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
from backend.core.intake import build_intake_snippet, normalize_intake
from backend.core.memory import (
    clear_chat,
    get_session_facts,
    get_session_intake,
    is_valid_session_id,
    load_chat_history,
    load_last_session,
    save_chat_message,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


def _format_facts_for_context(facts: dict) -> str:
    """Format cross-session facts into a concise string for the LLM."""
    if not facts:
        return ""
    parts = []
    for key, value in facts.items():
        if key == "updated_at":
            continue
        if value not in (None, "", [], {}):
            label = key.replace("_", " ").title()
            parts.append(f"{label}: {value}")
    return "Cross-session memory: " + "; ".join(parts) if parts else ""


@router.post("", response_model=ChatResponse)
async def chat(body: ChatRequest):
    message = body.message.strip()
    session_id = body.session_id.strip()
    topic = body.topic.strip()
    profile = body.profile.strip()
    # Structured intake from the client, normalized before any agent sees it.
    intake = normalize_intake(body.intake)

    if not message:
        return {"reply": "Please type a question first.", "session_id": session_id, "history_count": 0}

    # Attach the latest written advisory + cross-session facts for this session
    # so the chat can answer "me" questions about the user's own report and
    # remember their business across conversations.
    advisory_context = ""
    facts_context = ""
    if session_id:
        try:
            prior = load_last_session(session_id)
            if prior:
                topic = topic or prior.get("topic", "")
                runs = prior.get("runs") or []
                latest = (runs[0].get("state") if runs else None) or prior.get("state") or {}
                advisory_context = (latest.get("final_report", "") or "")[:3000]
                profile = profile or (latest.get("profile", "") or "")
                if not intake:
                    intake = normalize_intake(
                        latest.get("intake", {}) or get_session_intake(session_id)
                    )

                # Cross-session memory: facts learned from earlier runs.
                facts = get_session_facts(session_id)
                if facts:
                    facts_context = _format_facts_for_context(facts)
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
            profile=profile or build_intake_snippet(intake),
            intake=intake,
            facts_context=facts_context,
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