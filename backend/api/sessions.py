"""sessions.py — REST endpoints for session management and history."""
import logging

from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    RunDetailResponse,
    RunsListResponse,
    SessionDeleteResponse,
    SessionExportResponse,
    SessionFactsResponse,
    SessionGateResponse,
    SessionResponse,
)
from backend.core.memory import (
    delete_session,
    get_runs_list,
    get_session_facts,
    get_session_intake,
    is_valid_session_id,
    load_chat_history,
    load_last_session,
    load_pending_gate_summary,
    load_run,
)

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

    # New format: get latest run from runs[]
    runs = data.get("runs", [])
    if runs:
        run = runs[0]
        return {
            "session_id": session_id,
            "topic": run.get("topic", ""),
            "final_report": run.get("final_report", ""),
            "simplified_report": run.get("simplified_report", ""),
            "updated_at": run.get("created_at"),
        }
    
    # Fallback: old format (should not happen after migration)
    state = data.get("state", {})
    return {
        "session_id": session_id,
        "topic": data.get("topic", ""),
        "final_report": state.get("final_report", ""),
        "simplified_report": state.get("simplified_report", ""),
        "updated_at": data.get("updated_at"),
    }


@router.get("/{session_id}/runs", response_model=RunsListResponse)
async def get_session_runs(session_id: str):
    """Return a lightweight list of all historical runs for a session.

    ``pending_gate`` carries the approval a parked run is waiting on: that run
    has no report yet, so without it the dashboard would look empty even though
    the product is waiting on the user.
    """
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No saved runs for this session.")
    try:
        runs = get_runs_list(session_id)
        pending = load_pending_gate_summary(session_id)
    except Exception as e:
        logger.error(f"Failed to list runs for {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load run history.")
    return {"runs": runs, "pending_gate": pending}


@router.get("/{session_id}/runs/{run_id}", response_model=RunDetailResponse)
async def get_session_run(session_id: str, run_id: str):
    """Load a specific historical run by run_id."""
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No such session.")
    if not run_id or not run_id.strip():
        raise HTTPException(status_code=422, detail="run_id is required.")
    try:
        run = load_run(session_id, run_id)
    except Exception as e:
        logger.error(f"Failed to load run {run_id} for {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load run.")
    
    if not run:
        raise HTTPException(status_code=404, detail="Run not found.")
    
    state = run.get("state", {})
    return {
        "session_id": session_id,
        "run_id": run_id,
        "topic": run.get("topic", ""),
        "final_report": state.get("final_report", ""),
        "simplified_report": state.get("simplified_report", ""),
        "eligibility": state.get("eligibility", {}) or {},
        # The run state calls it `ledger`; the advisory JSON calls it
        # `action_ledger`. Accept both so the history view shows the score.
        "action_ledger": state.get("action_ledger") or state.get("ledger") or {},
        "scheme_choice": state.get("scheme_choice") or {},
        "plan": state.get("plan") or {},
        "plan_run": state.get("plan_run") or {},
        "intake": state.get("intake", {}) or {},
        "profile": state.get("profile", ""),
        "sources": state.get("sources", []) or [],
        "token_usage": state.get("token_usage", {}) or {},
        "engine": state.get("engine", ""),
        "created_at": run.get("updated_at"),
    }


@router.get("/{session_id}/gate", response_model=SessionGateResponse)
async def get_session_gate(session_id: str):
    """
    The approval gate waiting on this session, if there is one.

    A run that parked at the gate produced no report, so the gate is the only
    thing left to show. This is how the user finds it again after a reload
    and decides it — the decision then resumes the parked run.
    """
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No saved approval for this session.")
    try:
        data = load_last_session(session_id) or {}
    except Exception as e:
        logger.error(f"Failed to load session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load session.")

    gate = data.get("gate") or {}
    if not isinstance(gate, dict) or not gate:
        raise HTTPException(status_code=404, detail="No saved approval for this session.")

    gates = data.get("gates") if isinstance(data.get("gates"), dict) else {}
    all_gates = [g for g in gates.values() if isinstance(g, dict)]

    return {
        "session_id": session_id,
        "gate": gate,
        "gates": all_gates,
        "topic": data.get("topic", ""),
        "intake": data.get("intake", {}) or {},
    }


@router.get("/{session_id}/facts", response_model=SessionFactsResponse)
async def get_session_facts_endpoint(session_id: str):
    """Return cross-session facts and persisted intake for advisor context."""
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No such session.")
    try:
        facts = get_session_facts(session_id)
        intake = get_session_intake(session_id)
    except Exception as e:
        logger.error(f"Failed to load facts for {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not load session facts.")
    return {"facts": facts, "intake": intake}


@router.get("/{session_id}/export", response_model=SessionExportResponse)
async def export_session(session_id: str):
    """Export one session (runs + facts + intake + chat) as a JSON download.

    This is the user-facing counterpart of the WS ``export_session`` command, so
    the "export anytime" promise is reachable from the UI.
    """
    import time as _time

    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No such session.")
    try:
        data = load_last_session(session_id)
    except Exception as e:
        logger.error(f"Failed to export session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not export session.")

    if not data:
        raise HTTPException(status_code=404, detail="No such session.")

    try:
        chat = load_chat_history(session_id, limit=1000)
    except Exception:
        chat = []

    runs = data.get("runs", []) or []
    raw_gates = data.get("gates")
    if isinstance(raw_gates, dict):
        gates = [g for g in raw_gates.values() if isinstance(g, dict)]
    elif isinstance(raw_gates, list):
        gates = [g for g in raw_gates if isinstance(g, dict)]
    else:
        gates = []
    return {
        "session_id": session_id,
        "exported_at": _time.time(),
        "topic": data.get("topic", ""),
        "run_count": len(runs),
        "runs": runs,
        "facts": data.get("facts", {}) or {},
        "intake": data.get("intake", {}) or {},
        "chat": chat,
        "gates": gates,
    }


@router.delete("/{session_id}", response_model=SessionDeleteResponse)
async def remove_session(session_id: str):
    """GDPR right-to-delete: permanently remove this session and its chat."""
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=404, detail="No such session.")
    try:
        delete_session(session_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="No such session.")
    except Exception as e:
        logger.error(f"Failed to delete session {session_id}: {e}")
        raise HTTPException(status_code=500, detail="Could not delete session.")
    return {"status": "deleted", "session_id": session_id}
