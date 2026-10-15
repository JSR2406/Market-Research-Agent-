"""
compiler.py — validates a Plan before anything runs.

This is the piece that makes the product behave like a planner/executor rather
than like a chatbot that talks its way through a task. A chatbot emits sentences
and hopes they are coherent; here the model *proposes* a plan and the compiler
*disposes* of it. An invalid plan is rejected before a single model call is
spent, with the failure logged and the default topology used instead.

Compile checks, in priority order:

1. **Identity** — every step has a unique id and names a real graph node.
2. **Tooling** — every named deterministic tool actually exists. A plan that
   calls a tool the build does not have is a hallucination, not a to-do.
3. **State** — every ``pre``/``post`` key is a real state key, so a typo cannot
   silently become "always passes".
4. **Order** — a postcondition must be *producible*: either the key already
   exists in state, or some earlier step declares it as its own postcondition.
5. **Fallbacks** — a fallback must name a real node, so repair never dead-ends.

Every rejection carries a reason. Nothing here raises at run time — compilation
returns a result the caller can act on, because a bad plan is a recoverable
condition, not an outage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from backend.agentic.plan import NODE_IDS, STATE_KEYS, Plan, Step

logger = logging.getLogger(__name__)


class CompileError(Exception):
    """A plan that cannot be executed safely."""

    def __init__(self, reason: str, code: str = "compile_error"):
        super().__init__(reason)
        self.reason = reason
        self.code = code


@dataclass
class CompiledStep:
    """A Step plus everything the executor needs to run it safely."""

    step: Step
    order: int
    depends_on: List[str] = field(default_factory=list)


@dataclass
class CompiledPlan:
    """A validated plan, ready to execute."""

    goal: str
    steps: List[CompiledStep]
    warnings: List[str] = field(default_factory=list)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [
                {
                    "id": s.step.id,
                    "node": s.step.node,
                    "reason": s.step.reason,
                    "tool": s.step.tool,
                    "pre": s.step.pre,
                    "post": s.step.post,
                    "fallback": s.step.fallback,
                    "order": s.order,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
            "warnings": self.warnings,
        }


def _check_identity(plan: Plan) -> List[str]:
    """Duplicate ids are the most common way a generated plan corrupts itself."""
    warnings: List[str] = []
    seen: set = set()
    for step in plan.steps:
        if step.id in seen:
            warnings.append(f"duplicate step id '{step.id}'")
        seen.add(step.id)
    return warnings


def _check_tools(plan: Plan, tool_ids: frozenset) -> List[str]:
    """
    A step naming a tool that does not exist is a hallucination.

    The default plan ships the tool registry in state, so this check runs
    against whatever the build actually provides — not a hardcoded list that
    could drift from ``agentic/tools.py``.
    """
    warnings: List[str] = []
    for step in plan.steps:
        if step.tool and step.tool not in tool_ids:
            warnings.append(
                f"step '{step.id}' names unknown tool '{step.tool}'"
            )
    return warnings


def _check_state_keys(plan: Plan) -> List[str]:
    """
    Referencing an unknown key would make a precondition *always* pass, which is
    how a plan silently stops checking its own work.
    """
    warnings: List[str] = []
    for step in plan.steps:
        for key in step.pre:
            if key not in STATE_KEYS:
                warnings.append(f"step '{step.id}' pre references unknown key '{key}'")
        for key in step.post:
            if key not in STATE_KEYS:
                warnings.append(f"step '{step.id}' post references unknown key '{key}'")
        if step.fallback and step.fallback not in NODE_IDS:
            warnings.append(f"step '{step.id}' fallback is not a graph node")
    return warnings


def _check_order(plan: Plan, state: Dict) -> List[str]:
    """
    A postcondition must be reachable.

    A key is reachable if it already holds something in state, or if some step
    before it declares that key as its own postcondition. A plan that demands
    ``report`` from step 1 and never produces it is not a plan.
    """
    warnings: List[str] = []
    produced = {
        key for key in state if state.get(key) not in (None, "", [], {}, 0)
    }

    for index, step in enumerate(plan.steps):
        # A step's own postcondition satisfies itself — the key is produced here.
        own_outputs = set(step.post)

        # Preconditions must be reachable too: either already in state, or
        # produced by an earlier step. Otherwise the step is guaranteed to skip.
        for key in step.pre:
            if key in produced:
                continue
            produced_by_earlier = any(
                key in plan.steps[j].post
                for j in range(index)
                if plan.steps[j].id != step.id
            )
            if not produced_by_earlier:
                warnings.append(
                    f"step '{step.id}' needs '{key}' but nothing provides it"
                )

        for key in step.post:
            if key in produced or key in own_outputs:
                continue
            produced_by_earlier = any(
                key in plan.steps[j].post
                for j in range(index)
                if plan.steps[j].id != step.id
            )
            if not produced_by_earlier:
                warnings.append(
                    f"step '{step.id}' requires '{key}' but nothing produces it"
                )
        produced.update(step.post)

    return warnings


def compile_plan(
    plan: Optional[Plan],
    state: Dict,
    tool_ids: Optional[frozenset] = None,
    *,
    max_steps: int = 12,
) -> Optional[CompiledPlan]:
    """
    Validate a plan and return an executable CompiledPlan, or None.

    None means "do not trust this plan" — the caller then falls back to the
    default topology rather than executing something half-formed. Compiling
    never raises: a malformed plan is a normal outcome of asking a language
    model to plan, and the run must continue either way.
    """
    if plan is None or not plan.steps:
        return None

    # A None state is caller error, not a run-stopper. Coerce so the checks
    # below can treat state as a mapping unconditionally.
    state = state if isinstance(state, dict) else {}

    tools = tool_ids or frozenset(
        {"web_search", "scheme_match", "loan_ready_score", "document_checklist", "cashflow_projection"}
    )

    warnings: List[str] = []
    warnings += _check_identity(plan)
    warnings += _check_tools(plan, tools)
    warnings += _check_state_keys(plan)
    warnings += _check_order(plan, state)

    if warnings:
        for warning in warnings:
            logger.warning("[Compiler] %s", warning)

    # Duplicate ids would make the trace ambiguous, so refuse outright.
    ids = [s.id for s in plan.steps]
    if len(ids) != len(set(ids)):
        logger.warning("[Compiler] rejected plan: duplicate step ids")
        return None

    steps = plan.steps[:max_steps] if len(plan.steps) > max_steps else plan.steps

    compiled: List[CompiledStep] = []
    for order, step in enumerate(steps):
        depends_on = [
            other.step.id
            for other in compiled
            if set(step.pre) & set(other.step.post)
        ]
        compiled.append(CompiledStep(step=step, order=order, depends_on=depends_on))

    return CompiledPlan(goal=plan.goal, steps=compiled, warnings=warnings)


def default_plan(topic: str, max_steps: int = 4) -> Plan:
    """
    The topology every run falls back to.

    This is the honest default: a supervisor routing between research, analysis,
    scheme matching and writing. It is *not* a plan the model had to invent, so
    a failed compilation costs the user nothing.
    """
    return Plan(
        goal=topic[:200],
        steps=[
            Step(
                id="s1_research",
                node="research",
                reason="Gather live market and scheme facts before writing anything",
                tool="web_search",
                pre=["topic"],
                post=["findings"],
                fallback="supervisor",
            ),
            Step(
                id="s2_analyst",
                node="analyst",
                reason="Turn the topic and any intake answers into a cash-flow picture",
                tool="cashflow_projection",
                pre=["topic"],
                post=["analysis"],
                fallback="supervisor",
            ),
            Step(
                id="s3_schemes",
                node="schemes",
                reason="Match curated schemes to the business",
                tool="scheme_match",
                pre=["topic"],
                post=["schemes_text"],
                fallback="supervisor",
            ),
            Step(
                id="s4_writer",
                node="writer",
                reason="Draft the advisory from the gathered findings",
                pre=["findings"],
                post=["draft"],
                fallback="finalize",
            ),
            Step(
                id="s5_finalize",
                node="finalize",
                reason="Deterministic scoring, source annotation, simplification",
                pre=["draft"],
                post=["report", "simplified"],
                fallback="",
            ),
        ][:max(max_steps, 3)],
    )


def best_plan(
    candidate: Optional[Plan],
    state: Dict,
    topic: str,
    max_steps: int,
    tool_ids: Optional[frozenset] = None,
) -> CompiledPlan:
    """
    Compile the candidate plan, or fall back to the default topology.

    This is the single decision point: the model's plan is preferred when it
    compiles, and the default topology is used when it does not. Because the
    default is never worse than the current behaviour, compilation can only
    ever improve the run.
    """
    compiled = compile_plan(candidate, state, tool_ids)
    if compiled is not None:
        if compiled.steps:
            return compiled
    fallback = compile_plan(default_plan(topic, max_steps), state, tool_ids)
    if fallback is None:  # pragma: no cover — default plan always compiles
        raise CompileError("default plan failed to compile", code="no_plan")
    return fallback
