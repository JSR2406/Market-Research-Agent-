"""
backend/api/chat.py — conversational advisor API with chat memory.

Endpoints:
- POST   /api/chat          send a message (uses + persists chat memory)
- GET    /api/chat/history  fetch remembered messages for a session
- DELETE /api/chat/{session_id}  clear chat memory (GDPR-aligned)

The chat never returns a hard failure: every response is a human-readable
reply, and the agent carries its own heuristic offline guarantee.
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from backend.agents.chat import chat_agent
from backend.core.memory import (
    clear_chat,
    load_chat_history,
    load_last_session,
    save_chat_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str = ""
    topic: str = ""
    lang: str = "auto"  # "auto" | "hi" | "en"


@router.post("")
async def chat(body: ChatRequest):
    message = body.message.strip()
    session_id = body.session_id.strip()
    topic = body.topic.strip()

    if not message:
        return {"reply": "Please type a question first.", "session_id": session_id, "history_count": 0}

    # Attach the latest written advisory (if any) for this session so the chat
    # can answer "me" questions about the user's own report.
    advisory_context = ""
    if session_id:
        try:
            prior = load_last_session(session_id)
            if prior:
                topic = topic or prior.get("topic", "")
                advisory_context = (prior.get("state", {}).get("final_report", "") or "")[:3000]
        except Exception as e:
            logger.error(f"[Chat] Failed to load advisory context for {session_id}: {e}")

    history = load_chat_history(session_id, limit=16) if session_id else []

    try:
        reply = await chat_agent(
            message,
            topic=topic,
            advisory_context=advisory_context,
            chat_history=history,
            lang=body.lang,
        )
    except Exception as e:
        logger.error(f"[Chat] chat_agent raised unexpectedly: {e}")
        reply = "I hit an unexpected error. Please try your question again."

    if session_id:
        save_chat_message(session_id, "user", message)
        save_chat_message(session_id, "assistant", reply)

    return {
        "reply": reply,
        "session_id": session_id,
        "history_count": len(history) + 2,
    }


@router.get("/history")
async def chat_history(session_id: str = ""):
    if not session_id:
        return {"messages": []}
    try:
        messages = load_chat_history(session_id, limit=50)
    except Exception as e:
        logger.error(f"[Chat] Failed to load history: {e}")
        messages = []
    return {"messages": messages}


@router.delete("/{session_id}")
async def delete_chat_route(session_id: str):
    try:
        clear_chat(session_id)
    except Exception as e:
        logger.error(f"[Chat] Failed to clear memory for {session_id}: {e}")
    return {"status": "cleared", "session_id": session_id}