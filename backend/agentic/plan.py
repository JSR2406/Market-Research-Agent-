"""
plan.py — the typed Plan intermediate representation.

A plan is not prose. Each step names *which* graph node performs the work,
*which* deterministic tool it calls, the preconditions that must already hold
in state, the postconditions that must hold afterwards, and the step to run
instead when a postcondition fails.

That is what makes the compiler possible. With a machine-readable plan, invalid
structure is rejected before a single model call is spent — which is the
difference between "the model decided what to do" and "the model proposed,
code disposed". The LLM only fills natural-language fields; it never decides
whether a step is permitted.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── the state keys a plan may reference ──────────────────────────────────────
# These are the keys of AgenticState that steps produce or consume. A plan
# referencing anything else is a bug, so it is caught at compile time.
STATE_KEYS: frozenset = frozenset(
    {
        "topic", "profile", "session_context", "max_steps", "eligibility_note",
        "output_lang", "plan", "iteration",
        "findings", "sources", "errors", "trace", "visited",
        "research_notes", "analysis", "schemes_text", "draft", "reflection",
        "reflected", "report", "simplified", "loan_ready_score",
        "compiled_plan", "plan_run",
        "next_action", "finished",
    }
)

# ── the graph nodes a plan may invoke ────────────────────────────────────────
# A step that names a node outside this set can never run.
NODE_IDS: frozenset = frozenset(
    {
        "planner", "supervisor", "research", "analyst", "schemes",
        "writer", "critic", "refine", "finalize",
    }
)


@dataclass(frozen=True)
class Step:
    """
    One unit of executable work.

    ``pre``  — state keys that must be truthy before this step may run.
    ``post`` — state keys that must be truthy after it. A step whose postcondition
               fails is either repaired via ``fallback`` or recorded as failed
               with a reason — never retried blindly.
    ``tool`` — a deterministic tool name (see agentic/tools.py) or "" when the
               step is LLM-only prose work.
    """

    id: str
    node: str
    reason: str = ""
    tool: str = ""
    args: Dict[str, Any] = field(default_factory=dict)
    pre: List[str] = field(default_factory=list)
    post: List[str] = field(default_factory=list)
    fallback: str = ""


@dataclass(frozen=True)
class Plan:
    """An ordered, typed plan of work for one advisory run."""

    goal: str = ""
    steps: List[Step] = field(default_factory=list)

    @property
    def step_count(self) -> int:
        return len(self.steps)


def to_step(raw: Dict[str, Any]) -> Optional[Step]:
    """
    Coerce one raw mapping into a Step, or None if it cannot be salvaged.

    Deliberately tolerant of the *shape* (extra keys are dropped, missing ones
    default) but strict about the *identity*: a step with no id or an unknown
    node is not a step, it is garbage.
    """
    if not isinstance(raw, dict):
        return None
    sid = str(raw.get("id") or "").strip()
    node = str(raw.get("node") or "").strip()
    if not sid or node not in NODE_IDS:
        return None

    def _keys(value: Any) -> List[str]:
        if isinstance(value, list):
            return [str(v) for v in value if isinstance(v, (str, int))]
        if isinstance(value, str) and value.strip():
            return [p.strip() for p in value.split(",") if p.strip()]
        return []

    tool = str(raw.get("tool") or "").strip()
    if tool.startswith("{") or tool.startswith("["):
        tool = ""  # a tool name is a bare identifier, never a JSON blob

    return Step(
        id=sid,
        node=node,
        reason=str(raw.get("reason") or "").strip(),
        tool=tool,
        args=raw.get("args") if isinstance(raw.get("args"), dict) else {},
        pre=_keys(raw.get("pre")),
        post=_keys(raw.get("post")),
        fallback=str(raw.get("fallback") or "").strip(),
    )


def parse_plan_json(text: Optional[str]) -> Optional[Plan]:
    """
    Turn a plan the model emitted into a typed Plan.

    Accepts either a bare list of steps or ``{"goal": ..., "steps": [...]}``.
    Returns None when nothing usable could be built — callers treat that as
    "use the default topology", never as an error worth failing the run over.
    """
    if not text:
        return None
    try:
        raw = json.loads(text)
    except Exception:
        logger.debug("[Plan] plan JSON was not parseable; using default topology")
        return None

    if isinstance(raw, dict):
        goal = str(raw.get("goal") or "").strip()
        raw_steps = raw.get("steps")
    elif isinstance(raw, list):
        goal = ""
        raw_steps = raw
    else:
        return None

    if not isinstance(raw_steps, list):
        return None

    steps = [s for s in (to_step(item) for item in raw_steps) if s is not None]
    if not steps:
        return None
    # Hard ceiling: a plan with more steps than this is a runaway generation,
    # not a plan. The default topology is always available as the fallback.
    return Plan(goal=goal, steps=steps[:12])


def plan_to_dict(plan: Plan) -> Dict[str, Any]:
    """Serialise a Plan back to JSON for the state and the trace."""
    return {
        "goal": plan.goal,
        "steps": [
            {
                "id": s.id,
                "node": s.node,
                "reason": s.reason,
                "tool": s.tool,
                "args": s.args,
                "pre": s.pre,
                "post": s.post,
                "fallback": s.fallback,
            }
            for s in plan.steps
        ],
    }
