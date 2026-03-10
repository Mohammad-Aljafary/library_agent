import os
import json
import asyncio
from pathlib import Path
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from sqlalchemy.orm import Session

from db.tables import Message, ToolCall, engine
from server.tools import make_tools


def get_llm(streaming=False):
    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=0,  # Zero temperature for consistent tool calling
        num_predict=2048,  # Increased for better reasoning
        streaming=streaming,
        format="",  # Ensure no JSON mode that could interfere
    )


def get_system_prompt() -> str:
    path = Path(__file__).parent.parent / "prompts" / "system_prompt.txt"
    return path.read_text()


def get_chat_history(db: Session, session_id: str, max_messages: int = 20) -> list:
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


def run_agent(user_message: str, session_id: str) -> str:
    """
    Run the agent with its own DB session so the work is never
    interrupted by FastAPI request-lifecycle cleanup.
    """
    db = Session(engine)
    try:
        tools = make_tools(db, session_id)
        llm = get_llm()

        agent = create_react_agent(llm, tools)

        # Save user message
        db.add(Message(session_id=session_id, role="user", content=user_message))
        db.commit()

        # Build message list with history
        history = get_chat_history(db, session_id)
        messages = [SystemMessage(content=get_system_prompt())] + history

        # DEBUG: Log the messages being sent to agent
        print(f"\n=== DEBUG: Messages sent to agent (session {session_id}) ===")
        for i, m in enumerate(messages):
            msg_type = type(m).__name__
            if isinstance(m, SystemMessage):
                print(f"  [{i}] SystemMessage: {m.content[:150]}...")
            elif isinstance(m, HumanMessage):
                print(f"  [{i}] HumanMessage: '{m.content}'")
            elif isinstance(m, AIMessage):
                content_preview = m.content[:100] if m.content else "<empty>"
                has_tools = bool(hasattr(m, 'tool_calls') and m.tool_calls)
                print(f"  [{i}] AIMessage: content='{content_preview}' has_tool_calls={has_tools}")
                if has_tools:
                    for tc in m.tool_calls:
                        print(f"      -> Tool: {tc.get('name')} args={tc.get('args')}")
            elif isinstance(m, ToolMessage):
                print(f"  [{i}] ToolMessage: name={m.name} content='{m.content[:100]}...'")
        print("=== END DEBUG ===\n")

        response = agent.invoke({"messages": messages})

        # DEBUG: Log all messages in response
        print(f"\n=== DEBUG: Agent Response for session {session_id} ===")
        for i, m in enumerate(response["messages"]):
            msg_type = type(m).__name__
            if isinstance(m, AIMessage):
                print(f"  [{i}] AIMessage: content='{m.content[:100]}...' has_tool_calls={bool(hasattr(m, 'tool_calls') and m.tool_calls)}")
                if hasattr(m, 'tool_calls') and m.tool_calls:
                    for tc in m.tool_calls:
                        print(f"      -> Tool: {tc.get('name')} with args {tc.get('args')}")
            elif isinstance(m, ToolMessage):
                print(f"  [{i}] ToolMessage: name={m.name} content='{m.content[:100]}...'")
            else:
                print(f"  [{i}] {msg_type}: {str(m)[:100]}")
        print("=== END DEBUG ===\n")

        # Extract the final clean AI response (excluding tool calls)
        ai_messages = []
        tool_results = []
        
        for m in response["messages"]:
            if isinstance(m, AIMessage):
                # Skip messages that are just tool calls (no text content)
                if hasattr(m, 'tool_calls') and m.tool_calls and not m.content:
                    continue
                # Skip messages with tool call syntax in content
                if m.content and not any(x in m.content for x in ['{"name":', '"parameters":', 'tool_calls']):
                    ai_messages.append(m)
            elif isinstance(m, ToolMessage):
                tool_results.append(m)
        
        # Get the final response, or create one from tool results if agent didn't generate one
        if ai_messages:
            assistant_reply = ai_messages[-1].content
        elif tool_results:
            # Fallback: if LLM didn't generate a final response, show the tool result
            last_tool = tool_results[-1]
            try:
                result_data = json.loads(last_tool.content)
                if isinstance(result_data, list) and len(result_data) > 0:
                    assistant_reply = f"Found {len(result_data)} results. Here they are: {last_tool.content}"
                else:
                    assistant_reply = f"Result: {last_tool.content}"
            except:
                assistant_reply = last_tool.content
        else:
            assistant_reply = "I couldn't process that request."

        # Save assistant message
        db.add(Message(session_id=session_id, role="assistant", content=assistant_reply))
        db.commit()

        return assistant_reply
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


async def run_agent_stream(user_message: str, session_id: str):
    """
    Stream agent responses for better UX.
    
    Note: With ReAct agents, we must wait for all tool calls to complete before
    streaming the final response. This ensures users only see clean results.
    """
    db = Session(engine)
    try:
        tools = make_tools(db, session_id)
        llm = get_llm(streaming=False)  # Disable LLM streaming to avoid showing reasoning
        agent = create_react_agent(llm, tools)

        # Save user message
        db.add(Message(session_id=session_id, role="user", content=user_message))
        db.commit()

        # Build message list with history
        history = get_chat_history(db, session_id)
        messages = [SystemMessage(content=get_system_prompt())] + history

        # Execute agent and get clean final response
        response = agent.invoke({"messages": messages})
        
        # Extract the final clean AI response (excluding tool calls)
        ai_messages = []
        tool_results = []
        
        for m in response["messages"]:
            if isinstance(m, AIMessage):
                # Skip messages that are just tool calls (no text content)
                if hasattr(m, 'tool_calls') and m.tool_calls and not m.content:
                    continue
                # Skip messages with tool call syntax in content
                if m.content and not any(x in m.content for x in ['{"name":', '"parameters":', 'tool_calls']):
                    ai_messages.append(m)
            elif isinstance(m, ToolMessage):
                tool_results.append(m)
        
        # Get the final response, or create one from tool results if agent didn't generate one
        if ai_messages:
            final_response = ai_messages[-1].content
        elif tool_results:
            # Fallback: if LLM didn't generate a final response, show the tool result
            last_tool = tool_results[-1]
            try:
                result_data = json.loads(last_tool.content)
                if isinstance(result_data, list) and len(result_data) > 0:
                    final_response = f"Found {len(result_data)} results: {last_tool.content}"
                else:
                    final_response = f"Result: {last_tool.content}"
            except:
                final_response = last_tool.content
        else:
            final_response = "I couldn't process that request."

        # Stream the clean response word by word for better UX
        words = final_response.split()
        for i, word in enumerate(words):
            await asyncio.sleep(0.03)  # Small delay for smooth appearance
            yield word + (" " if i < len(words) - 1 else "")

        # Save assistant message
        db.add(Message(session_id=session_id, role="assistant", content=final_response))
        db.commit()
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()
