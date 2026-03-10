const API = "";
let currentSession = null;

// Track in-flight /chat requests per session so we can:
//  - block duplicate sends for the same session
//  - restore the typing indicator when revisiting a session still generating
const inFlight = new Map();   // sessionId → true

const messagesEl  = document.getElementById("messages");
const inputEl     = document.getElementById("user-input");
const sendBtn     = document.getElementById("send-btn");
const sessionList = document.getElementById("session-list");
const newBtn      = document.getElementById("new-session-btn");
const statusDot   = document.getElementById("status-dot");
const statusText  = document.getElementById("status-text");
const quickBtns   = document.querySelectorAll(".quick-btn");

// ── Sessions ──────────────────────────────────────────────
async function loadSessions() {
  try {
    const res      = await fetch(`${API}/sessions`);
    const sessions = await res.json();
    sessionList.innerHTML = "";
    sessions.reverse().forEach(id => {
      const btn = document.createElement("button");
      btn.className   = "session-item" + (id === currentSession ? " active" : "");
      
      // Session text
      const textSpan = document.createElement("span");
      textSpan.className = "session-text";
      textSpan.textContent = "💬 " + id.slice(0, 20) + "...";
      textSpan.title = id;
      textSpan.onclick = () => loadSession(id);
      
      // Delete button
      const deleteBtn = document.createElement("button");
      deleteBtn.className = "delete-session-btn";
      deleteBtn.innerHTML = "🗑️";
      deleteBtn.title = "Delete session";
      deleteBtn.onclick = (e) => {
        e.stopPropagation();
        deleteSession(id);
      };
      
      btn.appendChild(textSpan);
      btn.appendChild(deleteBtn);
      sessionList.appendChild(btn);
    });
  } catch {}
}

async function deleteSession(sessionId) {
  if (!confirm("Delete this session? This cannot be undone.")) return;
  
  try {
    await fetch(`${API}/session/${sessionId}`, { method: "DELETE" });
    
    // If we deleted the current session, show empty state
    if (currentSession === sessionId) {
      currentSession = null;
      sendBtn.disabled = true;
      messagesEl.innerHTML = "";
      showEmptyState();
      setStatus("active", "Select or start a session");
    }
    
    // Reload session list
    await loadSessions();
  } catch (e) {
    alert("Failed to delete session");
  }
}

async function loadSession(sessionId) {
  currentSession = sessionId;
  messagesEl.innerHTML = "";
  setStatus("active", "Session loaded");
  await loadSessions();

  const res      = await fetch(`${API}/session/${sessionId}/messages`);
  const messages = await res.json();

  // Guard: user may have switched away while we were fetching messages
  if (currentSession !== sessionId) return;

  if (messages.length === 0) {
    showEmptyState();
  } else {
    messages.forEach(m => appendMessage(m.role, m.content));
  }

  // If this session still has a request in-flight, show the typing indicator
  // and keep the send button disabled so the user knows it's still working.
  if (inFlight.has(sessionId)) {
    showTyping();
    sendBtn.disabled = true;
    setStatus("active", "Agent is thinking...");
  } else {
    sendBtn.disabled = false;
  }
}

async function newSession() {
  const res        = await fetch(`${API}/session/new`, { method: "POST" });
  const data       = await res.json();
  const newId      = data.session_id;
  currentSession   = newId;
  sendBtn.disabled = false;
  messagesEl.innerHTML = "";
  showEmptyState();
  setStatus("active", "New session started");
  await loadSessions();

  // Guard: user may have switched away while loadSessions ran
  if (currentSession !== newId) return;
  inputEl.focus();
}

// ── Messages ──────────────────────────────────────────────
function formatContent(content) {
  // Convert newlines to <br> and preserve formatting
  console.log('Formatting content:', content.substring(0, 100), 'has newlines:', content.includes('\n'));
  return content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
}

function appendMessage(role, content) {
  // remove empty state if present
  const empty = messagesEl.querySelector(".empty-state");
  if (empty) empty.remove();

  const row    = document.createElement("div");
  row.className = `message-row ${role}`;

  const avatar  = document.createElement("div");
  avatar.className = `avatar ${role === "user" ? "user-avatar" : "agent-avatar"}`;
  avatar.textContent = role === "user" ? "👤" : "📚";

  const bubble  = document.createElement("div");
  bubble.className  = "bubble";
  bubble.innerHTML = formatContent(content);

  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return bubble;
}

function showTyping() {
  // Prevent duplicate typing indicators
  if (document.getElementById("typing-row")) return;

  const empty = messagesEl.querySelector(".empty-state");
  if (empty) empty.remove();

  const row    = document.createElement("div");
  row.className = "message-row assistant";
  row.id        = "typing-row";

  const avatar  = document.createElement("div");
  avatar.className  = "avatar agent-avatar";
  avatar.textContent = "📚";

  const bubble  = document.createElement("div");
  bubble.className  = "bubble typing-indicator";
  bubble.innerHTML  = "<span></span><span></span><span></span>";

  row.appendChild(avatar);
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function removeTyping() {
  const row = document.getElementById("typing-row");
  if (row) row.remove();
}

function showEmptyState() {
  messagesEl.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📖</div>
      <p>Ask anything about books, orders, or inventory</p>
    </div>`;
}

// ── Send ──────────────────────────────────────────────────
async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || !currentSession) return;

  const targetSession = currentSession;

  // Block if this session already has a request in-flight
  if (inFlight.has(targetSession)) return;

  inputEl.value = "";
  inputEl.style.height = "auto";
  sendBtn.disabled = true;
  appendMessage("user", text);
  showTyping();
  setStatus("active", "Agent is thinking...");

  // Mark this session as having an in-flight request
  inFlight.set(targetSession, true);

  try {
    const response = await fetch(`${API}/chat/stream`, {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ session_id: targetSession, message: text }),
    });

    if (!response.ok) throw new Error("Server error");

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    
    // Remove typing and create response bubble
    if (currentSession === targetSession) {
      removeTyping();
    }
    const bubble = appendMessage("assistant", "");
    let fullText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value);
      const lines = chunk.split("\n");
      
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          try {
            const data = JSON.parse(line.slice(6));
            if (data.error) {
              throw new Error(data.error);
            }
            if (data.text) {
              fullText += data.text;
              // Only update UI if still on same session
              if (currentSession === targetSession) {
                bubble.innerHTML = formatContent(fullText);
                messagesEl.scrollTop = messagesEl.scrollHeight;
              }
            }
          } catch (parseError) {
            // Skip malformed JSON
          }
        }
      }
    }

    if (currentSession === targetSession) {
      setStatus("active", "Ready");
    }
    // If user switched away, the reply is already saved server-side
  } catch (e) {
    if (currentSession === targetSession) {
      removeTyping();
      appendMessage("assistant", "⚠️ Error: could not reach the server.");
      setStatus("error", "Connection error");
    }
  } finally {
    inFlight.delete(targetSession);
    if (currentSession === targetSession) {
      sendBtn.disabled = false;
      inputEl.focus();
    }
  }
}

// ── Status ────────────────────────────────────────────────
function setStatus(state, text) {
  statusDot.className = "";
  if (state === "active")  statusDot.classList.add("online");
  statusText.textContent = text;
}

// ── Auto-resize textarea ──────────────────────────────────
inputEl.addEventListener("input", () => {
  inputEl.style.height = "auto";
  inputEl.style.height = inputEl.scrollHeight + "px";
});

// ── Event Listeners ───────────────────────────────────────
sendBtn.onclick = sendMessage;
newBtn.onclick  = newSession;

inputEl.addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

quickBtns.forEach(btn => {
  btn.onclick = () => {
    if (!currentSession) return;
    inputEl.value = btn.dataset.prompt;
    sendMessage();
  };
});

// ── Init ─────────────────────────────────────────────────
loadSessions();
