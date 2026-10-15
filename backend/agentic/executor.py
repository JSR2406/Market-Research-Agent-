"""
executor.py — runs a CompiledPlan transactionally.

The difference between "an agent that tried" and "an executor" is that an
executor *checks its own work*. Every step declares what must be true before it
runs (``pre``) and what must be true afterwards (``post``). When a postcondition
fails the executor does not just move on and pretend: it either runs the step's
``fallback`` or records the failure with a reason, so the trace always shows
what actually happened.

Failure semantics, in priority order:

1. **Precondition unmet** → skip the step, record why. Never run work that
   cannot succeed.
2. **Postcondition unmet after running** → run the fallback, then record the
   outcome either way.
3. **Exception** → record, continue. A plan must never take the run down.

The executor never raises. It returns a ``PlanRun`` describing what happened,
which is what the graph writes into state and what the UI shows.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from backend.agentic.compiler import CompiledPlan, CompiledStep
from backend.agentic.events import EventEmitter
from backend.agentic.plan import plan_to_dict

logger = logging.getLogger(__name__)

SKIPPED = "skipped"
DONE = "done"
FAILED = "failed"
FALLBACK_USED = "fallback_used"


@dataclass
class StepResult:
    step_id: str
    node: str
    status: str
    pre_met: List[str] = field(default_factory=list)
    pre_unmet: List[str] = field(default_factory=list)
    post_met: List[str] = field(default_factory=list)
    post_unmet: List[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "node": self.node,
            "status": self.status,
            "pre_met": self.pre_met,
            "pre_unmet": self.pre_unmet,
            "post_met": self.post_met,
            "post_unmet": self.post_unmet,
            "reason": self.reason,
        }


@dataclass
class PlanRun:
    """What actually happened when a plan ran."""

    goal: str
    results: List[StepResult] = field(default_factory=list)

    @property
    def completed(self) -> List[str]:
        return [r.step_id for r in self.results if r.status == DONE]

    @property
    def failed(self) -> List[str]:
        return [r.step_id for r in self.results if r.status == FAILED]

    @property
    def ok(self) -> bool:
        return bool(self.results) and not self.failed

    def as_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "ok": self.ok,
            "completed": self.completed,
            "failed": self.failed,
            "results": [r.as_dict() for r in self.results],
        }


async def _run_node(
    node: str,
    state: Dict,
    config: Dict,
) -> Dict[str, Any]:
    """
    Invoke one graph node through the same router the native runner uses.

    Both runners share ``NODE_FUNCS``, so executing a plan produces exactly the
    state and events the rest of the graph would — the plan is an *order* over
    the same work, not a parallel implementation of it.
    """
    from backend.agentic.graph import NODE_FUNCS

    fn = NODE_FUNCS.get(node)
    if fn is None:
        raise RuntimeError(f"unknown node '{node}'")
    return await fn(state, config)


async def run_plan(
    compiled: CompiledPlan,
    state: Dict,
    config: Dict,
    emitter: EventEmitter,
    *,
    max_steps: int = 12,
) -> PlanRun:
    """
    Execute a compiled plan against the live graph state.

    ``config`` is the LangGraph-style config carrying the emitter; the node
    function is resolved from the shared ``NODE_FUNCS`` registry so a plan step
    and a graph node are literally the same code.
    """
    results: List[StepResult] = []

    for compiled_step in compiled.steps:
        if len(results) >= max_steps:
            logger.warning("[Executor] plan step cap reached at %d", max_steps)
            break

        step = compiled_step.step
        pre_met = [k for k in step.pre if state.get(k) not in (None, "", [], {}, 0)]
        pre_unmet = [k for k in step.pre if k not in pre_met]

        if pre_unmet:
            results.append(
                StepResult(
                    step_id=step.id,
                    node=step.node,
                    status=SKIPPED,
                    pre_met=pre_met,
                    pre_unmet=pre_unmet,
                    reason=f"preconditions unmet: {', '.join(pre_unmet)}",
                )
            )
            logger.warning(
                "[Executor] skipped %s — needs %s", step.id, ", ".join(pre_unmet)
            )
            continue

        try:
            update = await _run_node(step.node, state, config) or {}
            for key, value in (update or {}).items():
                reducer = _REDUCERS.get(key)
                if reducer and isinstance(state.get(key), list) and isinstance(value, list):
                    state[key] = state[key] + value
                else:
                    state[key] = value

            post_met = [k for k in step.post if state.get(k) not in (None, "", [], {}, 0)]
            post_unmet = [k for k in step.post if k not in post_met]

            if not post_unmet:
                results.append(
                    StepResult(
                        step_id=step.id,
                        node=step.node,
                        status=DONE,
                        pre_met=pre_met,
                        post_met=post_met,
                    )
                )
                continue

            # Postcondition failed — repair via the declared fallback, then
            # report the outcome honestly either way.
            if step.fallback and step.fallback != step.node:
                logger.warning(
                    "[Executor] %s produced nothing for %s; running fallback %s",
                    step.id,
                    ", ".join(post_unmet),
                    step.fallback,
                )
                try:
                    fallback_update = await _run_node(step.fallback, state, config) or {}
                    for key, value in (fallback_update or {}).items():
                        reducer = _REDUCERS.get(key)
                        if (
                            reducer
                            and isinstance(state.get(key), list)
                            and isinstance(value, list)
                        ):
                            state[key] = state[key] + value
                        else:
                            state[key] = value
                    still_missing = [
                        k
                        for k in step.post
                        if state.get(k) in (None, "", [], {}, 0)
                    ]
                    results.append(
                        StepResult(
                            step_id=step.id,
                            node=step.node,
                            status=FALLBACK_USED if not still_missing else FAILED,
                            pre_met=pre_met,
                            post_met=[k for k in step.post if k not in still_missing],
                            post_unmet=still_missing,
                            reason=(
                                f"postconditions still unmet after fallback: "
                                f"{', '.join(still_missing)}"
                                if still_missing
                                else "postcondition failed; fallback recovered it"
                            ),
                        )
                    )
                except Exception as exc:  # pragma: no cover — defensive
                    logger.exception("[Executor] fallback for %s failed", step.id)
                    results.append(
                        StepResult(
                            step_id=step.id,
                            node=step.node,
                            status=FAILED,
                            pre_met=pre_met,
                            post_unmet=post_unmet,
                            reason=f"fallback raised: {type(exc).__name__}",
                        )
                    )
            else:
                results.append(
                    StepResult(
                        step_id=step.id,
                        node=step.node,
                        status=FAILED,
                        pre_met=pre_met,
                        post_unmet=post_unmet,
                        reason=f"postconditions unmet: {', '.join(post_unmet)}",
                    )
                )
        except Exception as exc:
            logger.exception("[Executor] step %s failed", step.id)
            results.append(
                StepResult(
                    step_id=step.id,
                    node=step.node,
                    status=FAILED,
                    pre_met=pre_met,
                    reason=f"node raised {type(exc).__name__}",
                )
            )

    run = PlanRun(goal=compiled.goal, results=results)
    state["plan_run"] = run.as_dict()
    state["finished"] = run.ok
    return run


# Append reducers, mirroring agentic.graph.REDUCERS so plan-driven updates
# merge identically to graph-driven ones.
_REDUCERS: Dict[str, Any] = {}

try:  # pragma: no cover — import guard; the reducer map is a plain dict
    from backend.agentic.graph import REDUCERS as _GRAPH_REDUCERS

    _REDUCERS = dict(_GRAPH_REDUCERS)
except Exception:  # pragma: no cover
    pass


def with_postconditions(
    fn: Callable[..., Awaitable[Dict]],
    node_name: str = "",
) -> Callable[..., Awaitable[Dict]]:
    """
    Wrap a node so its plan step's postconditions are checked after it runs.

    This is what makes the run an *execution* rather than an attempt: every step
    declared what it would produce, and afterwards we check whether it did. The
    outcome is recorded in ``state["plan_run"]`` so the trace always shows what
    actually happened — including steps that quietly produced nothing.

    Applied to both runners, so LangGraph mode and the native fallback behave
    identically. The wrapper reads the live state at call time, so nothing needs
    to be bound when the graph is built.

    ``node_name`` is the graph node this function implements. It is passed
    explicitly rather than inferred from the function name, because a wrapper
    cannot reliably guess which node it is decorating.
    """

    # Typed as RunnableConfig because LangGraph inspects the signature to decide
    # how to invoke the node; a plain Dict hint makes it omit the config.
    try:
        from langchain_core.runnables import RunnableConfig
    except Exception:  # pragma: no cover — langchain-core absent → native runner
        RunnableConfig = dict  # type: ignore

    async def wrapped(node_state: Dict, config: Optional[RunnableConfig] = None) -> Dict:
        update = await fn(node_state, config) or {}
        compiled = node_state.get("compiled_plan")
        if not compiled:
            return update

        step = _matching_step(compiled, node_name or getattr(fn, "__name__", ""))
        if step is None:
            return update

        post = step.get("post") or []
        met = [k for k in post if node_state.get(k) not in (None, "", [], {}, 0)]
        unmet = [k for k in post if k not in met]
        record_step_result(
            node_state,
            step_id=step.get("id", ""),
            node=step.get("node", ""),
            status=DONE if not unmet else FAILED,
            post_met=met,
            post_unmet=unmet,
            reason="" if not unmet else f"postconditions unmet: {', '.join(unmet)}",
        )
        return update

    return wrapped


def _matching_step(compiled: Dict, fn_name: str) -> Optional[Dict]:
    """Find the compiled step whose node is about to run (or just ran)."""
    for step in reversed(compiled.get("steps") or []):
        if step.get("node") in fn_name or fn_name.endswith(step.get("node", "")):
            return step
    return None


def record_step_result(
    state: Dict,
    *,
    step_id: str,
    node: str,
    status: str,
    pre_met: Optional[List[str]] = None,
    pre_unmet: Optional[List[str]] = None,
    post_met: Optional[List[str]] = None,
    post_unmet: Optional[List[str]] = None,
    reason: str = "",
) -> None:
    """Append one step outcome to ``state["plan_run"]["results"]``."""
    run = state.setdefault("plan_run", {"goal": "", "ok": False, "results": []})
    if "results" not in run or not isinstance(run["results"], list):
        run["results"] = []
    run["results"].append(
        {
            "step_id": step_id,
            "node": node,
            "status": status,
            "pre_met": pre_met or [],
            "pre_unmet": pre_unmet or [],
            "post_met": post_met or [],
            "post_unmet": post_unmet or [],
            "reason": reason,
        }
    )
    failed = [r for r in run["results"] if r.get("status") == FAILED]
    run["ok"] = bool(run["results"]) and not failed


def plan_run_summary(run: PlanRun) -> str:
    """One plain-language line for the report footer and the trace."""
    if run.ok:
        return f"All {len(run.results)} planned steps completed."
    failed = ", ".join(run.failed) or "none"
    return f"{len(run.completed)}/{len(run.results)} steps completed; failed: {failed}."
