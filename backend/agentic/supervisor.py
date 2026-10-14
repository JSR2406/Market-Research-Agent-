"""
backend/agentic/supervisor.py — the agentic routing brain.

The supervisor inspects the shared state and decides which node runs next
(ReAct-style control flow). It asks the LLM for a strict-JSON decision and
*always* has a deterministic policy fallback, so routing keeps working when
every provider is offline (offline guarantee) and cannot be hijacked into an
invalid state (guardrails enforce prerequisites).

Action space:
    research | analyze | schemes | write | critique | finish
"""
from __future__ import annotations

import json
import logging
import re
from typing import Dict, List, Tuple

from backend.core.config import AGENTIC_MAX_ITERATIONS
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

ACTIONS: List[str] = ["research", "analyze", "schemes", "write", "finish"]

# Which node each action maps to in the graph. (Reflection/critique is handled
# by the writer→critic→refine edges, not by a supervisor action.)
ACTION_TO_NODE: Dict[str, str] = {
    "research": "research",
    "analyze": "analyst",
    "schemes": "schemes",
    "write": "writer",
    "finish": "finalize",
}

_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def _done_summary(state: Dict) -> str:
    done = []
    if state.get("research_notes"):
        done.append("research")
    if state.get("analysis"):
        done.append("cash-flow analysis")
    if state.get("schemes_text"):
        done.append("scheme matching")
    if state.get("draft"):
        done.append("draft report")
    return ", ".join(done) if done else "nothing yet"


def heuristic_action(state: Dict) -> Tuple[str, str]:
    """Deterministic policy — mirrors (and improves on) the legacy keyword routing."""
    if not state.get("research_notes"):
        return "research", "No research gathered yet — start by gathering facts."
    if not state.get("analysis"):
        return "analyze", "Research is in; build the cash-flow analysis."
    if not state.get("schemes_text"):
        return "schemes", "Match government schemes to the business profile."
    if not state.get("draft"):
        return "write", "Enough findings collected — draft the advisory."
    return "finish", "Draft exists — finalize and simplify."


def _guard(action: str, state: Dict) -> Tuple[str, str]:
    """Reject actions whose prerequisites aren't met; fall back to policy."""
    if action not in ACTIONS:
        return heuristic_action(state)
    hops = int(state.get("iteration", 0))
    if hops >= AGENTIC_MAX_ITERATIONS:
        # Budget exhausted — force synthesis/finish.
        if not state.get("draft"):
            return "write", "Iteration budget reached — write the report now."
        return "finish", "Iteration budget reached — finalize now."
    if action == "write" and not (state.get("research_notes") or state.get("analysis")):
        return "research", "Cannot write yet — gather findings first."
    if action in ("schemes",) and not state.get("research_notes"):
        return "research", "Research before matching schemes."
    if action == "finish" and not state.get("draft"):
        return "write", "No draft yet — write before finishing."
    return action, ""


def _parse_decision(text: str) -> Tuple[str, str]:
    match = _JSON_RE.search(text or "")
    if not match:
        raise ValueError("no JSON in supervisor output")
    data = json.loads(match.group(0))
    action = str(data.get("action", "")).strip().lower()
    reason = str(data.get("reason", "") or "").strip()
    return action, reason


async def decide(state: Dict) -> Tuple[str, str]:
    """Return (action, reason). Never raises."""
    fallback_action, fallback_reason = heuristic_action(state)
    try:
        compact_findings = " | ".join(
            f"{f.get('step', '')[:50]}: {str(f.get('output', ''))[:120]}"
            for f in (state.get("findings") or [])[-4:]
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the supervisor of a multi-agent loan-advisory team for "
                    "Indian micro-entrepreneurs. Decide the SINGLE best next action. "
                    f"Valid actions: {ACTIONS}. "
                    "Rules: gather research before analysis; analyse before matching "
                    "schemes; only write when you have enough findings; critique the "
                    "draft once before finishing; finish means produce the final report. "
                    'Reply ONLY as JSON: {"action": "<action>", "reason": "<one short sentence>"}.'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Business topic: {state.get('topic', '')[:600]}\n"
                    f"Plan: {state.get('plan') or []}\n"
                    f"Already done: {_done_summary(state)}\n"
                    f"Hop {int(state.get('iteration', 0)) + 1} of {AGENTIC_MAX_ITERATIONS}.\n"
                    f"Recent findings: {compact_findings or 'none'}\n"
                    f"Reflection notes: {str(state.get('reflection', ''))[:200] or 'none'}\n"
                    "What is the next action?"
                ),
            },
        ]
        raw = await call_llm(messages, temperature=0.2, max_tokens=200, agent_hint="supervisor")
        action, reason = _parse_decision(raw)
        action, guard_reason = _guard(action, state)
        return action, reason or guard_reason or fallback_reason
    except Exception as e:
        logger.info("[Supervisor] LLM decision failed (%s) — using deterministic policy.", e)
        return fallback_action, fallback_reason
