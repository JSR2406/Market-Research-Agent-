"""
executor.py — thin adapter that runs the agentic advisory graph over a WebSocket.

The orchestration itself now lives in ``backend/agentic`` (a LangGraph
StateGraph, with a native fallback runner). This module keeps its historical
entry point — ``run_research_workflow`` — so the WebSocket layer and session
persistence are unchanged, and it still owns the deterministic finalize pass
(``_finalize_report``) that the agentic ``finalize`` node reuses.

Event contract: the agentic engine emits status/graph/plan/node_start/node_end/
thought/tool_call/tool_result/reflection/token_usage live; this module emits the
terminal ``done`` event (with the full agentic trace) and persists the session.
"""
import logging

import json
from typing import Dict, List, Optional

from backend.agentic import EventEmitter, run_agentic_workflow
from backend.agentic import engine_name
from backend.core.eligibility import (
    eligibility_note_for,
    evaluate_schemes,
)
from backend.core.intake import build_intake_snippet, normalize_intake
from backend.core.ledger import ledger_and_score
from backend.core.llm_client import SESSION_TOKEN_USAGE, reset_session_state

logger = logging.getLogger(__name__)


def _finalize_report(
    report: str,
    sources: list | None = None,
    eligibility: dict | None = None,
    ledger: dict | None = None,
) -> str:
    """
    Single deterministic post-pass on the LLM-written advisory:
    1. attach the loan-ready score — from the Action Ledger when we have one,
       so the score measures the user's real progress rather than the quality
       of the model's own prose (the older rubric handed out points for having
       written a summary and listed five documents),
    2. annotate every matched-scheme line with its official source URL +
       last-verified date from schemes.json (never trusts the model), and
    3. attach the run's genuinely-fetched source URLs under `sources`,
    4. attach the deterministic eligibility verdicts and the action ledger, so
       the UI renders computed facts rather than anything the model claimed.

    Runs exactly once so a re-parse cannot drop the injected score.
    """
    if not report:
        return report
    from backend.core.heuristics import (
        annotate_scheme_sources,
        compute_loan_ready_score,
        parse_advisory_json,
    )
    data = parse_advisory_json(report)  # normalized — handles fences, prose, junk
    if data is None:
        return report
    if "loan_ready_score" not in data:
        data["loan_ready_score"] = ledger if ledger else compute_loan_ready_score(data)
    schemes = data.get("matched_schemes") or []
    if schemes:
        data["matched_schemes"] = annotate_scheme_sources([str(s) for s in schemes])
    if sources:
        data["sources"] = sources
    if eligibility:
        data["eligibility"] = {
            "business_class": eligibility.get("business_class", ""),
            "business_label": eligibility.get("business_label", ""),
            "amount": eligibility.get("amount"),
            "families": eligibility.get("families") or [],
        }
    if ledger:
        data["action_ledger"] = {
            "score": ledger.get("score", 0),
            "points_earned": ledger.get("points_earned", 0),
            "points_possible": ledger.get("points_possible", 100),
            "reasons": ledger.get("reasons") or [],
            "next_action": ledger.get("next_action"),
            "blockers": ledger.get("blockers") or [],
            "actions": ledger.get("actions") or [],
            "done_count": ledger.get("done_count", 0),
            "total_count": ledger.get("total_count", 0),
        }
    return json.dumps(data, ensure_ascii=False)


async def run_research_workflow(
    topic: str,
    max_steps: int,
    websocket,
    cancel_flag: dict,
    session_context: str = "",
    session_id: str = "",
    profile: str = "",
    intake: Optional[Dict[str, str]] = None,
) -> None:
    """
    Run the agentic advisory graph. ``session_context`` is an optional string
    injected by ws_market.py when a previous session is resumed.

    ``intake`` is the structured Business Check-up answers ({field_id: text}).
    This is the single intake layer: the canonical snippet built from it is what
    the run topic, the synthesis prompts and the advisor chat all consume, so the
    written advisory and any follow-up question answer agree. ``profile`` is the
    legacy flat-string form and is only used when no structured intake arrived.
    """
    reset_session_state()

    # One canonical profile string, built once, from the structured answers.
    profile = build_intake_snippet(intake) or (profile or "").strip()

    # Collect genuinely-fetched research source URLs for provenance on `done`.
    from backend.core.web_research import set_run_source_sink

    source_sink: list = []
    set_run_source_sink(source_sink)

    # Guarantee the profile is present in the run topic even if the caller
    # only sent it as a separate field (never duplicate it if already folded in).
    if profile and profile not in topic:
        topic = f"{profile}. {topic}"

    # Normalized once here so what we persist matches what the graph saw.
    intake_answers = normalize_intake(intake)

    # ── Deterministic verdicts, computed BEFORE any LLM call ────────────────
    # The rule engine decides what this business can and cannot do. The model
    # only ever writes prose around these numbers, so it cannot invent an
    # eligibility claim or soften a disqualification.
    #
    # Progress the user already ticked on previous visits is carried forward,
    # so the loan-ready score climbs as they actually do things.
    completed_actions: List[str] = []
    if session_id:
        try:
            from backend.core.memory import load_last_session as _prior_session

            prior_state = (_prior_session(session_id) or {}).get("state") or {}
            completed_actions = list((prior_state.get("ledger") or {}).get("completed") or [])
        except Exception:
            logger.warning("Could not read prior ledger for %s", session_id, exc_info=True)
            completed_actions = []

    eligibility = evaluate_schemes(intake_answers, topic)
    scored = ledger_and_score(intake_answers, topic, completed=completed_actions, eligibility=eligibility)
    eligibility_note = eligibility_note_for(eligibility)

    emitter = EventEmitter(websocket, cancel_flag)
    emitter.set_token_usage_getter(lambda: SESSION_TOKEN_USAGE)

    try:
        state, status = await run_agentic_workflow(
            topic,
            max_steps,
            emitter,
            session_context=session_context,
            profile=profile,
            session_id=session_id,
            eligibility_note=eligibility_note,
        )
    finally:
        set_run_source_sink(None)

    if status in ("cancelled", "error"):
        # The engine already emitted the terminal event.
        return

    final_report = _finalize_report(
        state.get("report") or "",
        sources=state.get("sources") or [],
        eligibility=eligibility,
        ledger=scored,
    )
    simplified_report = state.get("simplified") or ""
    plan_steps = state.get("plan") or []
    findings = state.get("findings") or []
    history = [
        (f.get("step", ""), f.get("agent", ""), f.get("output", ""))
        for f in findings
    ]

    await emitter.send({
        "type": "token_usage",
        "input_tokens": SESSION_TOKEN_USAGE["input"],
        "output_tokens": SESSION_TOKEN_USAGE["output"],
        "total_tokens": SESSION_TOKEN_USAGE["total"],
    })
    await emitter.send({
        "type": "done",
        "topic": topic,
        "final_report": final_report,
        "simplified_report": simplified_report,
        "token_usage": SESSION_TOKEN_USAGE.copy(),
        "trace": emitter.trace,
        "engine": engine_name(),
    })

    logger.info(
        "Agentic run complete | engine=%s | total token usage ~%s",
        engine_name(),
        SESSION_TOKEN_USAGE["total"],
    )

    # Save the session when a session_id is provided.
    if session_id:
        try:
            from backend.core.memory import save_session

            state_out = {
                "plan": plan_steps,
                "history": history,
                "final_report": final_report,
                "simplified_report": simplified_report,
                "token_usage": SESSION_TOKEN_USAGE.copy(),
                "profile": profile,
                "intake": intake_answers,
                "eligibility": {
                    "business_class": eligibility.get("business_class", ""),
                    "business_label": eligibility.get("business_label", ""),
                    "amount": eligibility.get("amount"),
                },
                "ledger": {"completed": completed_actions, "score": scored.get("score", 0)},
                "trace": emitter.trace,
                "engine": engine_name(),
                "visited": state.get("visited") or [],
            }
            save_session(session_id, topic, state_out)
        except Exception as e:
            logger.error("Failed to save session %s: %s", session_id, e)
