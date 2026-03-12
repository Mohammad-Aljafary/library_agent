import os
import json
import asyncio
from pathlib import Path
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from sqlalchemy.orm import Session

from db.tables import Message, ToolCall, engine
from server.tools import make_tools, set_active_validator
from server.tool_validator import ToolCallValidator

def get_llm(streaming=False):
    return ChatOllama(
        model=os.environ["OLLAMA_MODEL"],
        base_url=os.environ["OLLAMA_BASE_URL"],
        temperature=float(os.environ.get("OLLAMA_TEMPERATURE", "0")),
        num_predict=int(os.environ.get("OLLAMA_NUM_PREDICT", "2048")),
        streaming=streaming,
        format="",
    )


def get_system_prompt() -> str:
    path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
    return path.read_text()


def get_chat_history(db: Session, session_id: str, max_messages: int = None) -> list:
    if max_messages is None:
        max_messages = int(os.environ.get("MAX_CHAT_HISTORY", "20"))
    """Build chat history including tool calls for conversational context.
    Limited to recent messages to reduce processing time.
    """
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at.desc())
        .limit(max_messages)
        .all()
    )
    messages.reverse()
    
    if not messages:
        return []
    
    earliest_msg_time = messages[0].created_at
    tool_calls = (
        db.query(ToolCall)
        .filter(ToolCall.session_id == session_id)
        .filter(ToolCall.created_at >= earliest_msg_time)
        .order_by(ToolCall.created_at)
        .all()
    )
    
    # Build a timeline of all events (messages and tool calls)
    events = []
    for m in messages:
        events.append(('msg', m.created_at, m))
    for tc in tool_calls:
        events.append(('tool', tc.created_at, tc))
    
    events.sort(key=lambda x: x[1])
    
    history = []
    pending_tool_calls = []
    
    for event_type, timestamp, data in events:
        if event_type == 'msg':
            m = data
            if m.role == "user":
                history.append(HumanMessage(content=m.content))
            elif m.role == "assistant":
                # If there are pending tool calls, attach them to this AI message
                if pending_tool_calls:
                    history.append(AIMessage(
                        content="",
                        tool_calls=pending_tool_calls
                    ))
                    pending_tool_calls = []
                
                # Add the assistant's text response
                history.append(AIMessage(content=m.content))
        
        elif event_type == 'tool':
            tc = data
            # Create a tool call record
            tool_call_id = f"call_{tc.id}"
            pending_tool_calls.append({
                "id": tool_call_id,
                "name": tc.name,
                "args": json.loads(tc.args_json)
            })
            # Add the tool result message
            history.append(ToolMessage(
                content=tc.result_json,
                tool_call_id=tool_call_id,
                name=tc.name
            ))
    
    return history


WRONG_TOOL_MARKER = "WRONG TOOL:"
MAX_WRONG_TOOL_RETRIES = 2

async def run_agent_stream(user_message: str, session_id: str):
    db = Session(engine)
    try:
        tools = make_tools(db, session_id)
        llm = get_llm(streaming=False)
        agent = create_react_agent(llm, tools)

        db.add(Message(session_id=session_id, role="user", content=user_message))
        db.commit()

        validator = ToolCallValidator(user_message)
        set_active_validator(validator)

        history = get_chat_history(db, session_id)
        messages = [SystemMessage(content=get_system_prompt())] + history

        # ── retry loop ────────────────────────────────────────────
        wrong_tool_retries = 0
        response = None

        while wrong_tool_retries <= MAX_WRONG_TOOL_RETRIES:
            response = agent.invoke(
                {"messages": messages},
                config={"recursion_limit": 10}   # prevent infinite tool loops
            )

            # check if any ToolMessage contains a wrong-tool error
            wrong_tool_errors = [
                m for m in response["messages"]
                if isinstance(m, ToolMessage)
                and WRONG_TOOL_MARKER in (m.content or "")
            ]

            if not wrong_tool_errors:
                break  # all good

            wrong_tool_retries += 1
            logger.warning(
                "Wrong tool error detected in ToolMessage (retry %d/%d): %s",
                wrong_tool_retries,
                MAX_WRONG_TOOL_RETRIES,
                wrong_tool_errors[-1].content[:120],
            )

            if wrong_tool_retries > MAX_WRONG_TOOL_RETRIES:
                logger.error("Max wrong-tool retries reached for session %s", session_id)
                break

            # feed the error back as context for the next attempt
            messages = messages + [
                HumanMessage(
                    content=(
                        f"You used the wrong tool. "
                        f"Error: {wrong_tool_errors[-1].content}. "
                        f"Please retry with the correct tool."
                    )
                )
            ]
        # ── end retry loop ────────────────────────────────────────

        # Extract final clean AI response
        ai_messages = []
        tool_results = []

        for m in response["messages"]:
            if isinstance(m, AIMessage):
                if hasattr(m, 'tool_calls') and m.tool_calls and not m.content:
                    continue
                if m.content and not any(
                    x in m.content for x in ['{"name":', '"parameters":', 'tool_calls']
                ):
                    ai_messages.append(m)
            elif isinstance(m, ToolMessage):
                # ── filter out wrong-tool errors from tool results ──
                if WRONG_TOOL_MARKER not in (m.content or ""):
                    tool_results.append(m)

        if ai_messages:
            final_response = ai_messages[-1].content
        elif tool_results:
            last_tool = tool_results[-1]
            try:
                result_data = json.loads(last_tool.content)
                if isinstance(result_data, list) and len(result_data) > 0:
                    final_response = f"Found {len(result_data)} results: {last_tool.content}"
                else:
                    final_response = f"Result: {last_tool.content}"
            except:
                final_response = last_tool.content
        elif wrong_tool_retries > MAX_WRONG_TOOL_RETRIES:
            # graceful degradation after exhausting retries
            final_response = "I'm sorry, I couldn't complete that action. Please rephrase your request."
        else:
            final_response = "I couldn't process that request."

        # Stream the clean response
        words = final_response.split()
        for i, word in enumerate(words):
            await asyncio.sleep(0.03)
            yield word + (" " if i < len(words) - 1 else "")

        db.add(Message(session_id=session_id, role="assistant", content=final_response))
        db.commit()

    except Exception as e:
        db.rollback()
        raise
    finally:
        set_active_validator(None)
        db.close()
