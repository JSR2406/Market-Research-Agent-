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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.agents.chat import chat_agent
from backend.api.schemas import (
    ChatDeleteResponse,
    ChatHistoryResponse,
    ChatRequest,
    ChatResponse,
)
from backend.core.memory import (
    clear_chat,
    is_valid_session_id,
    load_chat_history,
    load_last_session,
    save_chat_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest):
    message = body.message.strip()
    session_id = body.session_id.strip()
    topic = body.topic.strip()
    profile = body.profile.strip()

    if not message:
        return {"reply": "Please type a question first.", "session_id": session_id, "history_count": 0}

    # Attach the latest written advisory (if any) for this session so the chat
    # can answer "me" questions about the user's own report. The Business Check-up
    # profile saved with the run is used when the client didn't send it.
    advisory_context = ""
    if session_id:
        try:
            prior = load_last_session(session_id)
            if prior:
                topic = topic or prior.get("topic", "")
                advisory_context = (prior.get("state", {}).get("final_report", "") or "")[:3000]
                profile = profile or (prior.get("state", {}).get("profile", "") or "")
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
            profile=profile,
        )
    except Exception as e:
        logger.error(f"[Chat] chat_agent raised unexpectedly: {e}")
        reply = "I hit an unexpected error. Please try your question again."

    if session_id:
        save_chat_message(session_id, "user", message)
        save_chat_message(session_id, "assistant", reply)

    return {
        "reply": reply,
        "session_id": session_id or "",
        "history_count": len(history) + 2 if session_id else 2,
    }


@router.get("/history", response_model=ChatHistoryResponse)
async def chat_history(session_id: str = ""):
    if not session_id:
        return {"messages": []}
    try:
        messages = load_chat_history(session_id, limit=50)
    except Exception as e:
        logger.error(f"[Chat] Failed to load history: {e}")
        messages = []
    return {"messages": messages}


@router.delete("/{session_id}", response_model=ChatDeleteResponse)
async def delete_chat_route(session_id: str):
    # P0: reject a bad session id up front instead of swallowing the failure
    # and reporting "cleared" when nothing was deleted.
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=422, detail="Invalid session id.")
    try:
        clear_chat(session_id)
    except Exception as e:
        logger.error(f"[Chat] Failed to clear memory for {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not clear chat memory. Please try again.")
    return {"status": "cleared", "session_id": session_id}