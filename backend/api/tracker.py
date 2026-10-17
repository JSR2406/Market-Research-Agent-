"""
backend/api/tracker.py — application tracker + deadline calendar (WS-6).

  GET  /api/deadlines             the curated deadline rows, with live state
  GET  /api/tracker/{session_id}  a session's applications + board + alert preview
  POST /api/tracker/{session_id}  save applications and alert settings

Everything here is deterministic and offline: the "closing soon" flag is date
arithmetic in ``backend.core.tracker``, and the curated deadlines come from
``backend/data/deadlines.json`` (each row cites a ``source_url``). No model is
asked for a date.

Storage is the per-session JSON file ``{session_id}_tracker.json``, guarded by
the same session-id allowlist as chat memory — so a user who opts in (they have a
session id) gets server-side persistence, and the delete/export paths already
cover it. The frontend also keeps a localStorage copy for a session-less visitor.
"""
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from backend.api.schemas import (
    DeadlineListResponse,
    TrackerResponse,
    TrackerRequest,
    TrackerStatusLabel,
)
from backend.core.memory import is_valid_session_id
from backend.core.tracker import (
    STATUSES,
    STATUS_LABELS,
    deadline_state,
    build_alerts,
    build_board,
    delete_tracker,
    load_deadlines,
    load_tracker,
    save_tracker,
    validate_alert,
    validate_applications,
    DISCLAIMER,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["tracker"])

_LANGS = {"en", "hi"}


def _lang(value: str) -> str:
    return value if value in _LANGS else "en"


def _status_labels(lang: str) -> list:
    return [
        TrackerStatusLabel(id=status, label=STATUS_LABELS[status][lang])
        for status in STATUSES
    ]


def _require_session(session_id: str) -> str:
    value = (session_id or "").strip()
    if not is_valid_session_id(value):
        raise HTTPException(status_code=422, detail="That session id is not valid.")
    return value


def _rows_with_state(rows: list, today: date, lang: str) -> list:
    """Attach the computed deadline state to public rows (same maths as the board)."""
    out = []
    for row in rows:
        out.append(
            {
                "scheme_id": row["scheme_id"],
                "kind": row["kind"],
                "date": row["date"],
                "title": row["title"].get(lang) or row["title"].get("en") or "",
                "note": row["note"].get(lang) or row["note"].get("en") or "",
                "source_url": row["source_url"],
                "last_verified_at": row["last_verified_at"],
                **deadline_state(row["date"], today, row["kind"], lang=lang),
            }
        )
    out.sort(key=lambda r: r["date"])
    return out


@router.get("/deadlines", response_model=DeadlineListResponse)
async def list_deadlines(lang: str = Query("en", max_length=8)):
    """
    The curated windows we can cite, classified for today.

    Programmes with no published closing date are deliberately absent rather than
    given an invented one; the tracker labels those ``rolling`` per scheme.
    """
    today = date.today()
    return DeadlineListResponse(
        deadlines=_rows_with_state(load_deadlines(), today, _lang(lang)),
        disclaimer=DISCLAIMER[_lang(lang)],
    )


def _build_response(session_id: str, applications: list, alert: dict, intake: dict, topic: str, lang: str) -> TrackerResponse:
    board = build_board(applications, None, lang)
    alerts = build_alerts(applications, board, _verified_snapshot(session_id), intake, topic, lang=lang)
    return TrackerResponse(
        session_id=session_id,
        applications=applications,
        board=board,
        alerts=alerts,
        alert=alert or {},
        statuses=_status_labels(lang),
        disclaimer=DISCLAIMER[lang],
    )


def _verified_snapshot(session_id: str) -> dict:
    """
    The ``last_verified_at`` we last showed this user per scheme.

    Held inside the tracker file's alert block so a re-verification can be
    detected on the next visit without a database.
    """
    stored = load_tracker(session_id).get("alert") or {}
    snapshot = stored.get("verified") if isinstance(stored, dict) else None
    return snapshot if isinstance(snapshot, dict) else {}


@router.get("/tracker/{session_id}", response_model=TrackerResponse)
async def get_tracker(session_id: str, lang: str = Query("en", max_length=8)):
    """Read a session's tracker. An empty session yields an empty board, not a 404."""
    clean = _require_session(session_id)
    language = _lang(lang)
    stored = load_tracker(clean)
    try:
        applications = validate_applications(stored.get("applications") or [])
    except ValueError:
        # A corrupt/hand-edited file must not break the page.
        logger.warning("[tracker] stored applications for %s were unusable", clean)
        applications = []
    alert = stored.get("alert") or {}
    return _build_response(clean, applications, alert, {}, "", language)


@router.post("/tracker/{session_id}", response_model=TrackerResponse)
async def save_session_tracker(session_id: str, req: TrackerRequest):
    """
    Persist the tracker and return the recomputed board + alert preview.

    Validation failures are 422 with a single human sentence — never a stack.
    """
    clean = _require_session(session_id)
    lang = _lang(req.lang)
    try:
        applications = validate_applications([a.model_dump() for a in req.applications])
        alert = validate_alert(req.alert.model_dump() if req.alert else None, lang)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Carry the re-verification snapshot forward so the *next* visit can tell
    # "our record changed since you last looked".
    previous = dict(_verified_snapshot(clean))
    snapshot = {a["scheme_id"]: a.get("last_verified_at", "") for a in applications if a.get("last_verified_at")}
    if alert:
        alert = {**alert, "verified": snapshot}

    try:
        if applications or alert:
            save_tracker(clean, applications, alert)
        else:
            delete_tracker(clean)
    except ValueError as exc:  # invalid id already handled; defensive
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError:
        logger.exception("[tracker] could not save tracker for %s", clean)
        return TrackerResponse(
            session_id=clean,
            applications=applications,
            board=build_board(applications, None, lang),
            statuses=_status_labels(lang),
            disclaimer=DISCLAIMER[lang],
            error="Could not save your tracker right now. Please try again.",
        )

    response = _build_response(clean, applications, alert, req.intake, req.topic, lang)
    response.alerts = build_alerts(applications, response.board, previous, req.intake, req.topic, lang=lang)
    return response
