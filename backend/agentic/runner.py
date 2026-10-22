"""
backend/agentic/graph.py — the advisory agent graph.

Defines the topology once (nodes + edges + conditional routers) and can compile
it to a real LangGraph ``StateGraph`` when ``langgraph`` is installed. The same
routers are consumed by the native runner, so the control flow is identical with
or without the dependency.

Topology:

    START → planner → [gate] → supervisor
    supervisor -cond-> research | analyst | schemes | [scheme_gate] → writer | finalize
    research | analyst | schemes → supervisor
    writer -cond-> critic (reflection) | refine
    critic -cond-> writer (revise) | refine
    refine → finalize → END

``[gate]`` is the human approval gate and ``[scheme_gate]`` the second one:
the user picks the scheme the advisory is built around. Both are only wired
into the graph when gates are switched on for the run — otherwise the topology
is exactly what it always was.

The scheme gate sits on the *only* edge into the writer that starts a new
draft, so the critic's revision loop never re-asks the user: the commitment
was made once.
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
    gate_node,
    planner_node,
    refine_node,
    research_node,
    scheme_gate_node,
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
    "gate": gate_node,
    "scheme_gate": scheme_gate_node,
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


def route_from_supervisor(state: Dict) -> str:
    action = str(state.get("next_action", "research"))
    return ACTION_TO_NODE.get(action, "research")


def make_supervisor_router(scheme_gate_enabled: bool) -> Callable[[Dict], str]:
    """
    The supervisor's router.

    When the scheme gate is on, the run does not go straight to the writer —
    it goes to the scheme gate first, so the user chooses the scheme before
    the report commits to one. Every other target is untouched.
    """

    def route(state: Dict) -> str:
        target = route_from_supervisor(state)
        if scheme_gate_enabled and target == "writer":
            return "scheme_gate"
        return target

    return route


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
        return "gate"
    if node == "gate":
        return "supervisor"
    if node == "supervisor":
        return route_from_supervisor(state)
    if node in ("research", "analyst", "schemes"):
        return "supervisor"
    if node == "scheme_gate":
        return "writer"
    if node == "writer":
        return route_after_writer(state)
    if node == "critic":
        return route_after_critic(state)
    if node == "refine":
        return "finalize"
    return None  # finalize → END


def graph_topology(gates_enabled: bool = False) -> Dict[str, Any]:
    """
    The nodes and edges for the UI.

    The approval gates are only part of the graph when gates are switched on —
    otherwise the run is exactly what it always was, and the trace does not
    show a node that does nothing.
    """
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
    if gates_enabled:
        nodes = [n for n in nodes if n["id"] not in ("gate", "scheme_gate")]
        nodes.insert(1, {"id": "gate", **NODE_META["gate"]})
        nodes.insert(2, {"id": "scheme_gate", **NODE_META["scheme_gate"]})
        edges = (
            [["planner", "gate"], ["gate", "supervisor"]]
            + [e for e in edges[1:] if e != ["supervisor", "writer"]]
            + [["supervisor", "scheme_gate"], ["scheme_gate", "writer"]]
        )
    else:
        nodes = [n for n in nodes if n["id"] not in ("gate", "scheme_gate")]
    return {"nodes": nodes, "edges": edges}


def build_langgraph(gates_enabled: bool = False) -> Any:
    """Compile the LangGraph StateGraph when the dependency is available."""
    if not LANGGRAPH_AVAILABLE:
        logger.warning("[graph] LangGraph unavailable; native execution path will be used.")
        return None

    from langgraph.graph import END, START, StateGraph
    from backend.agentic.state import AgenticState

    g = StateGraph(AgenticState)
    node_funcs = dict(NODE_FUNCS)
    if not gates_enabled:
        node_funcs.pop("gate", None)
        node_funcs.pop("scheme_gate", None)
    for nid, fn in node_funcs.items():
        g.add_node(nid, with_postconditions(fn, nid))

    g.add_edge(START, "planner")
    if gates_enabled:
        g.add_edge("planner", "gate")
        g.add_edge("gate", "supervisor")
    else:
        g.add_edge("planner", "supervisor")
    targets = ["research", "analyst", "schemes", "writer", "finalize"]
    if gates_enabled:
        targets.append("scheme_gate")
    g.add_conditional_edges(
        "supervisor",
        make_supervisor_router(bool(gates_enabled)),
        {k: k for k in targets},
    )
    for nid in ("research", "analyst", "schemes"):
        g.add_edge(nid, "supervisor")
    if gates_enabled:
        g.add_edge("scheme_gate", "writer")
    g.add_conditional_edges("writer", route_after_writer, {"critic": "critic", "refine": "refine"})
    g.add_conditional_edges("critic", route_after_critic, {"writer": "writer", "refine": "refine"})
    g.add_edge("refine", "finalize")
    g.add_edge("finalize", END)

    return g.compile()
