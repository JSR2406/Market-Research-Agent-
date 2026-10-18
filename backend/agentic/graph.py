"""
backend/agentic/graph.py — the advisory agent graph.

Defines the topology once (nodes + edges + conditional routers) and can compile
it to a real LangGraph ``StateGraph`` when ``langgraph`` is installed. The same
routers are consumed by the native runner, so the control flow is identical with
or without the dependency.

Topology:

    START → planner → supervisor
    supervisor -cond-> research | analyst | schemes | writer | finalize
    research | analyst | schemes → supervisor
    writer -cond-> critic (reflection) | refine
    critic -cond-> writer (revise) | refine
    refine → finalize → END
"""
from __future__ import annotations

import logging
import operator
from typing import Any, Callable, Dict, List, Optional

from backend.agentic.events import EventEmitter, WorkflowCancelled
from backend.agentic.executor import with_postconditions
from backend.agentic.nodes import (
    NODE_META,
    analyst_node,
    critic_node,
    finalize_node,
    planner_node,
    refine_node,
    research_node,
    schemes_node,
    supervisor_node,
    writer_node,
)
from backend.agentic.runtime import LANGGRAPH_AVAILABLE
from backend.agentic.supervisor import ACTION_TO_NODE
from backend.core.config import AGENTIC_MAX_ITERATIONS, AGENTIC_REFLECTION_ENABLED

logger = logging.getLogger(__name__)

NODE_FUNCS: Dict[str, Callable] = {
    "planner": planner_node,
    "supervisor": supervisor_node,
    "research": research_node,
    "analyst": analyst_node,
    "schemes": schemes_node,
    "writer": writer_node,
    "critic": critic_node,
    "refine": refine_node,
    "finalize": finalize_node,
}

# List fields use append reducers (matching AgenticState's Annotated types).
REDUCERS = {
    "plan": operator.add,
    "findings": operator.add,
    "sources": operator.add,
    "errors": operator.add,
    "trace": operator.add,
    "visited": operator.add,
}

START_NODE = "planner"


# ── conditional routers (shared by both runners) ──────────────────────────────

def route_from_supervisor(state: Dict) -> str:
    action = str(state.get("next_action", "research"))
    return ACTION_TO_NODE.get(action, "research")


def route_after_writer(state: Dict) -> str:
    if AGENTIC_REFLECTION_ENABLED and int(state.get("reflected", 0)) < 2:
        return "critic"
    return "refine"


def route_after_critic(state: Dict) -> str:
    verdict = str(state.get("critique_verdict", "pass"))
    if (
        verdict in ("revise", "research")
        and int(state.get("iteration", 0)) < AGENTIC_MAX_ITERATIONS
        and int(state.get("reflected", 0)) < 2
    ):
        return "writer"
    return "refine"


def successors(node: str, state: Dict) -> Optional[str]:
    """Next node for the native runner; None means END."""
    if node == "planner":
        return "supervisor"
    if node == "supervisor":
        return route_from_supervisor(state)
    if node in ("research", "analyst", "schemes"):
        return "supervisor"
    if node == "writer":
        return route_after_writer(state)
    if node == "critic":
        return route_after_critic(state)
    if node == "refine":
        return "finalize"
    return None  # finalize → END


# ── topology metadata for the UI ─────────────────────────────────────────────

def graph_topology() -> Dict[str, Any]:
    nodes = [{"id": nid, **meta} for nid, meta in NODE_META.items()]
    edges = [
        ["planner", "supervisor"],
        ["supervisor", "research"],
        ["supervisor", "analyst"],
        ["supervisor", "schemes"],
        ["supervisor", "writer"],
        ["supervisor", "finalize"],
        ["research", "supervisor"],
        ["analyst", "supervisor"],
        ["schemes", "supervisor"],
        ["writer", "critic"],
        ["writer", "refine"],
        ["critic", "writer"],
        ["critic", "refine"],
        ["refine", "finalize"],
        ["finalize", "END"],
    ]
    return {"nodes": nodes, "edges": edges}


# ── LangGraph builder ─────────────────────────────────────────────────────────

def build_langgraph() -> Any:
    """Compile the LangGraph StateGraph. langgraph is required — always compiles."""
    from langgraph.graph import END, START, StateGraph

    from backend.agentic.state import AgenticState

    g = StateGraph(AgenticState)
    for nid, fn in NODE_FUNCS.items():
        # Postcondition checking is applied so the compiled graph behaves
        # identically to the node spec. The wrapper reads live state at call time.
        g.add_node(nid, with_postconditions(fn, nid))

    g.add_edge(START, "planner")
    g.add_edge("planner", "supervisor")
    g.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {k: k for k in ("research", "analyst", "schemes", "writer", "finalize")},
    )
    for nid in ("research", "analyst", "schemes"):
        g.add_edge(nid, "supervisor")
    g.add_conditional_edges("writer", route_after_writer, {"critic": "critic", "refine": "refine"})
    g.add_conditional_edges("critic", route_after_critic, {"writer": "writer", "refine": "refine"})
    g.add_edge("refine", "finalize")
    g.add_edge("finalize", END)

    return g.compile()
