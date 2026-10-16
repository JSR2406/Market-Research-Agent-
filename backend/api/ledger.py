"""
backend/api/ledger.py — deterministic eligibility + the Action Ledger.

These two endpoints are the deterministic half of the product, exposed on
their own so the UI can show a verdict the moment the user answers the
Business Check-up — without waiting for (or spending on) an agent run.

  POST /api/eligibility     rule-engine verdicts for one business
  GET  /api/ledger/{sid}    current ledger + loan-ready score for a session
  POST /api/ledger/{sid}    tick actions off; the score updates immediately

Everything returned here is computed in code from schemes.json plus the user's
own answers. No LLM is involved, so these endpoints answer identically whether
every provider is up or all of them are down.
"""
import logging

from fastapi import APIRouter, HTTPException

from backend.api.schemas import (
    EligibilityRequest,
    EligibilityResponse,
    LedgerResponse,
    LedgerTickRequest,
)
from backend.core.eligibility import (
    evaluate_schemes,
    eligibility_summary,
)
from backend.core.intake import coverage_report, next_probe, normalize_intake, question_pack
from backend.core.ledger import ledger_and_score, merge_completed
from backend.core.memory import is_valid_session_id, load_session_state

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["ledger"])


def _session_state(session_id: str) -> dict:
    if not session_id:
        return {}
    try:
        return load_session_state(session_id)
    except Exception as e:
        logger.error("[Ledger] failed to load session %s: %s", session_id, e)
        return {}


@router.post("/eligibility", response_model=EligibilityResponse)
async def eligibility(body: EligibilityRequest):
    """Rule-engine verdicts — can say no, with a cited reason."""
    intake = normalize_intake(body.intake)
    result = evaluate_schemes(intake, body.topic, body.amount, body.lang)
    return {
        "business_class": result.get("business_class", ""),
        "business_label": result.get("business_label", ""),
        "signals": result.get("signals") or [],
        "amount": result.get("amount"),
        "families": result.get("families") or [],
        "summary": eligibility_summary(result),
        "coverage": coverage_report(intake, body.lang),
        "next_probe": next_probe(intake, body.lang),
        # Question wording in the site's language, so the stepper can render the
        # same branching questions the backend reasons about.
        "questions": question_pack(body.lang),
    }


@router.get("/ledger/{session_id}", response_model=LedgerResponse)
async def get_ledger(session_id: str):
    """The user's current ledger and loan-ready score."""
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=422, detail="Invalid session id.")
    state = _session_state(session_id)
    scored = ledger_and_score(
        normalize_intake(state.get("intake")),
        state.get("topic", ""),
        completed=(state.get("ledger") or {}).get("completed") or [],
    )
    return {"session_id": session_id, **scored}


@router.post("/ledger/{session_id}", response_model=LedgerResponse)
async def tick_ledger(session_id: str, body: LedgerTickRequest):
    """
    Mark actions complete. The score is recomputed from the merged list, so
    the gain is visible immediately and survives to the next advisory run.
    """
    if not is_valid_session_id(session_id):
        raise HTTPException(status_code=422, detail="Invalid session id.")

    state = _session_state(session_id)
    prior = (state.get("ledger") or {}).get("completed") or []
    # Ticking is monotonic — progress is never silently revoked by a stale client.
    completed = merge_completed(prior, body.completed)

    scored = ledger_and_score(
        normalize_intake(state.get("intake")),
        state.get("topic", ""),
        completed=completed,
    )

    if body.persist:
        try:
            from backend.core.memory import update_session_state

            # Patch the newest run in place — ticking progress must not create a
            # phantom entry in the run history.
            update_session_state(
                session_id,
                {"ledger": {"completed": completed, "score": scored.get("score", 0)}},
            )
        except Exception as e:
            logger.error("[Ledger] failed to persist progress for %s: %s", session_id, e)

    return {"session_id": session_id, **scored, "completed": completed}