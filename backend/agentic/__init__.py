"""
backend/agentic — the LangGraph-based agentic advisory engine.

Public surface:
    run_agentic_workflow(topic, max_steps, emitter, ...) -> (state, status)
    build_langgraph()          compiled StateGraph or None
    graph_topology()           {nodes, edges} for the UI
    EventEmitter               real-time event sink
    LANGGRAPH_AVAILABLE        engine availability flag

The engine is self-contained: the graph, nodes, tools and event protocol all
live here, so ``backend.workflows.executor`` becomes a thin adapter.
"""
from backend.agentic.events import EventEmitter, WorkflowCancelled
from backend.agentic.graph import build_langgraph, graph_topology
from backend.agentic.plan import Plan, Step, parse_plan_json
from backend.agentic.compiler import CompiledPlan, best_plan, compile_plan
from backend.agentic.executor import PlanRun, run_plan, with_postconditions
from backend.agentic.runner import run_agentic_workflow
from backend.agentic.runtime import LANGGRAPH_AVAILABLE, LANGCHAIN_AVAILABLE, engine_name
from backend.agentic.state import AgenticState, initial_state

__all__ = [
    "EventEmitter",
    "WorkflowCancelled",
    "build_langgraph",
    "graph_topology",
    "run_agentic_workflow",
    "LANGGRAPH_AVAILABLE",
    "LANGCHAIN_AVAILABLE",
    "engine_name",
    "AgenticState",
    "initial_state",
    "Plan",
    "Step",
    "parse_plan_json",
    "CompiledPlan",
    "best_plan",
    "compile_plan",
    "PlanRun",
    "run_plan",
    "with_postconditions",
]
