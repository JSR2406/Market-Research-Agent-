"""sessions.py — REST endpoint to reopen a saved advisory for a session_id."""
import logging

from fastapi import APIRouter, HTTPException

from backend.api.schemas import SessionResponse
from backend.core.memory import is_valid_session_id, load_last_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str):
    """Return the latest saved advisory for a session so it can be resumed.

    A session that does not exist (or an id that fails the allowlist guard) is
    reported as 404 — the frontend treats it as "nothing to resume".
    """
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No saved advisory for this session.")
    try:
        data = load_last_session(session_id)
    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load session.")

    if not data:
        raise HTTPException(status_code=404, detail="No saved advisory for this session.")

    state = data.get("state", {})
    return {
        "session_id": session_id,
        "topic": data.get("topic", ""),
        "final_report": state.get("final_report", ""),
        "simplified_report": state.get("simplified_report", ""),
        "updated_at": data.get("updated_at"),
    }