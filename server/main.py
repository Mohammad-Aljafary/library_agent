import uuid
import json
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pyrate_limiter import Duration, Limiter, Rate
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from db.tables import get_session, init_db, Message, ToolCall
from db.seed import seed_data
from server.agent import  run_agent_stream

limiter = Limiter(Rate(50, Duration.MINUTE))


class RateLimiterMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        if not limiter.try_acquire(client_ip):
            return JSONResponse({"detail": "Too many requests"}, status_code=429)
        return await call_next(request)


app = FastAPI(title="Library Desk Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimiterMiddleware)


@app.on_event("startup")
def startup():
    seed_data()


# ── Health check ───────────────────────────────────────────
@app.get("/health")
def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {
        "status": "healthy",
        "service": "library-desk-agent",
        "version": "1.0.0"
    }


# ── Schemas ────────────────────────────────────────────────
class ChatRequest(BaseModel):
    session_id: str
    message: str


class SessionResponse(BaseModel):
    session_id: str


# ── Session endpoints ──────────────────────────────────────
@app.post("/session/new", response_model=SessionResponse)
def new_session():
    return {"session_id": str(uuid.uuid4())}


@app.get("/sessions")
def list_sessions(db: Session = Depends(get_session)):
    rows = db.query(Message.session_id).distinct().all()
    return [r[0] for r in rows]


@app.get("/session/{session_id}/messages")
def get_messages(session_id: str, db: Session = Depends(get_session)):
    messages = (
        db.query(Message)
        .filter(Message.session_id == session_id)
        .order_by(Message.created_at)
        .all()
    )
    return [
        {"role": m.role, "content": m.content, "created_at": str(m.created_at)}
        for m in messages
    ]


# ── Chat endpoint ──────────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Stream responses for better perceived speed."""
    async def generate():
        try:
            async for chunk in run_agent_stream(req.message, req.session_id):
                yield f"data: {json.dumps({'text': chunk})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")


@app.delete("/session/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_session)):
    """Delete a session and all its associated messages and tool calls."""
    db.query(ToolCall).filter(ToolCall.session_id == session_id).delete()
    db.query(Message).filter(Message.session_id == session_id).delete()
    db.commit()
    return {"status": "deleted", "session_id": session_id}


# ── Serve frontend ─────────────────────────────────────────
app.mount("/", StaticFiles(directory="app", html=True), name="frontend")

