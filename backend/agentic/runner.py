"""
backend/agentic/runner.py — executes the agent graph.

Two interchangeable runners produce identical state and identical real-time
events:

  1. **LangGraph runner** — used when ``langgraph`` is importable. Compiles the
     StateGraph from ``graph.py`` and invokes it; nodes stream events themselves.
  2. **Native runner** — a tiny async loop over the same node functions + routers
     (``successors``). Used when LangGraph is absent, so the offline guarantee
     holds even in a minimal install.

``run_agentic_workflow`` picks the best available runner and never raises: it
returns ``(final_state, status)`` where status ∈ {"done", "cancelled", "error"}.
"""
from __future__ import annotations

import asyncio
import logging
import operator
from typing import Any, Dict, Optional, Tuple

from backend.agentic import runtime
from backend.agentic.events import EventEmitter, WorkflowCancelled
from backend.agentic.graph import NODE_FUNCS, REDUCERS, START_NODE, graph_topology, successors
from backend.agentic.state import AgenticState, initial_state

logger = logging.getLogger(__name__)


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


async def _run_native(state: Dict, config: Dict) -> Tuple[Dict, str]:
    """Pure-asyncio execution of the same graph spec."""
    em: EventEmitter = config["configurable"]["emitter"]
    node: Optional[str] = START_NODE
    guard = 0
    while node is not None:
        guard += 1
        if guard > 64:  # hard safety net against an accidental cycle
            logger.error("[Agentic] native runner exceeded node guard")
            break
        if em.is_cancelled:
            raise WorkflowCancelled()
        fn = NODE_FUNCS.get(node)
        if fn is None:
            logger.error("[Agentic] unknown node %s", node)
            break
        update = await fn(state, config)
        _merge(state, update)
        node = successors(node, state)
    return state, "done"


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
) -> Tuple[AgenticState, str]:
    """Run the advisory graph end-to-end. Never raises — returns (state, status)."""
    state = initial_state(topic, max_steps, profile, session_context, eligibility_note)
    state["output_lang"] = output_lang
    config: Dict[str, Any] = {
        "configurable": {
            "emitter": emitter,
            "thread_id": session_id or "adhoc-session",
        }
    }

    engine = runtime.engine_name()
    topo = graph_topology()
    await emitter.graph(engine, topo["nodes"], topo["edges"])
    await emitter.status("Understanding your business…")

    compiled = None
    if runtime.LANGGRAPH_AVAILABLE:
        from backend.agentic.graph import build_langgraph

        compiled = build_langgraph()

    try:
        if compiled is not None:
            final_state, status = await _run_langgraph(state, config, compiled)
        else:
            final_state, status = await _run_native(state, config)
        return final_state, status
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
