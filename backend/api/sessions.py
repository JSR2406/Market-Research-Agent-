"""sessions.py — REST endpoint to reopen a saved advisory for a session_id."""
import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str):
    """Return the latest saved advisory for a session so it can be resumed."""
    try:
        from backend.core.memory import load_last_session
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