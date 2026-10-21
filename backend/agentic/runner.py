"""
backend/agentic/runner.py — executes the agent graph via LangGraph.

LangGraph is the REQUIRED execution engine. ``run_agentic_workflow`` compiles
the StateGraph from ``graph.py`` and invokes it; nodes stream real-time events
through the shared ``EventEmitter``. Never raises — returns
``(final_state, status)`` where status ∈ {"done", "cancelled", "error", "paused"}.

``paused`` means the run stopped at a human approval gate and is waiting for
the user to decide. It is a normal outcome, not a failure: the gate is already
persisted, so the user can answer it later and the run resumes.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional, Tuple

from backend.agentic import runtime
from backend.agentic.events import EventEmitter, GatePaused, WorkflowCancelled
from backend.agentic.executor import with_postconditions
from backend.agentic.graph import NODE_FUNCS, REDUCERS, START_NODE, graph_topology
from backend.agentic.state import AgenticState, initial_state

logger = logging.getLogger(__name__)

# The same registry, wrapped for postcondition checking. The compiled LangGraph
# executes through this surface, so a step's declared postconditions get checked.
POSTCONDITION_FUNCS: Dict[str, Any] = {
    nid: with_postconditions(fn, nid) for nid, fn in NODE_FUNCS.items()
}


def _merge(state: Dict, update: Optional[Dict]) -> None:
    """Merge a node's returned update into state honoring append reducers."""
    if not update:
        return
    for key, value in update.items():
        reducer = REDUCERS.get(key)
        if reducer is not None and isinstance(state.get(key), list) and isinstance(value, list):
            state[key] = state[key] + value
        else:
            state[key] = value


async def _run_langgraph(state: Dict, config: Dict, graph: Any) -> Tuple[Dict, str]:
    """Execute the compiled LangGraph; nodes emit events themselves."""
    em: EventEmitter = config["configurable"]["emitter"]
    if em.is_cancelled:
        raise WorkflowCancelled()
    result = await graph.ainvoke(state, config=config)
    return dict(result), "done"


async def run_agentic_workflow(
    topic: str,
    max_steps: int,
    emitter: EventEmitter,
    session_context: str = "",
    profile: str = "",
    session_id: str = "",
    eligibility_note: str = "",
    output_lang: str = "en",
    *,
    intake: Optional[Dict[str, str]] = None,
    eligibility_families: Optional[list] = None,
    gates_enabled: bool = False,
    gate_broker: Any = None,
    gate: Optional[Dict[str, Any]] = None,
    gate_decision: Optional[Dict[str, Any]] = None,
) -> Tuple[AgenticState, str]:
    """Run the advisory graph end-to-end via LangGraph. Never raises."""
    state = initial_state(
        topic,
        max_steps,
        profile,
        session_context,
        eligibility_note,
        intake=intake,
        eligibility_families=eligibility_families,
        gate=gate,
        gate_decision=gate_decision,
    )
    state["output_lang"] = output_lang
    config: Dict[str, Any] = {
        "configurable": {
            "emitter": emitter,
            "thread_id": session_id or "adhoc-session",
            "session_id": session_id,
            "gates_enabled": bool(gates_enabled),
            "gate_broker": gate_broker,
        }
    }

    engine = runtime.engine_name()
    topo = graph_topology(gates_enabled=bool(gates_enabled))
    await emitter.graph(engine, topo["nodes"], topo["edges"])
    await emitter.status("Understanding your business…")

    from backend.agentic.graph import build_langgraph

    compiled = build_langgraph(gates_enabled=bool(gates_enabled))

    try:
        final_state, status = await _run_langgraph(state, config, compiled)
        return final_state, status
    except GatePaused as paused:
        # The run is waiting for a human decision. The gate is already on disk;
        # the caller tells the user and parks the run.
        logger.info("[Agentic] workflow paused at a gate: %s", paused.status)
        state["gate"] = paused.gate
        return state, "paused"
    except WorkflowCancelled:
        logger.info("[Agentic] workflow cancelled by user")
        await emitter.cancelled()
        return state, "cancelled"
    except asyncio.CancelledError:
        logger.info("[Agentic] workflow task cancelled")
        try:
            await emitter.cancelled()
        except Exception:
            pass
        raise
    except Exception as e:
        logger.exception("[Agentic] workflow failed: %s", e)
        await emitter.error("We could not finish your research. Please try again.")
        return state, "error"
