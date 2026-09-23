"""
backend/workflows/routing.py — static policy for mapping a plan step to an agent.

Replaces the old `decide_agent` LLM call (1 wasted call per step) with a
zero-cost keyword matcher. Callers that want an explicit mix can import
AGENT_REGISTRY or SYNTHESIS_AGENTS directly.
"""
from typing import List, Tuple

from backend.agents.analyst import analyst_agent
from backend.agents.editor import editor_agent
from backend.agents.opportunity import opportunity_agent
from backend.agents.research import research_agent
from backend.agents.writer import writer_agent

AGENT_REGISTRY = {
    "research_agent": research_agent,
    "analyst_agent": analyst_agent,
    "opportunity_agent": opportunity_agent,
    "writer_agent": writer_agent,
    "editor_agent": editor_agent,
}

# These agents are not run per-step; they are run once at the end of the workflow.
SYNTHESIS_AGENTS = {"writer_agent", "editor_agent"}

_ROUTING_RULES: List[Tuple[List[str], str]] = [
    (["research", "scrape", "gather", "data", "source", "find", "retrieve"], "research_agent"),
    (["analys", "metric", "tam", "sam", "cagr", "swot", "segment", "competitor"], "analyst_agent"),
    (["opportunit", "ai/ml", "product", "solution", "strateg", "recommend"], "opportunity_agent"),
    (["write", "draft", "report", "synthesize", "compile", "summarize"], "writer_agent"),
    (["edit", "polish", "refine", "review", "improve", "finalize"], "editor_agent"),
]


def route_step(step: str) -> str:
    """Map a plan step string to an agent name using keyword matching."""
    lower = step.lower()
    for keywords, agent_name in _ROUTING_RULES:
        if any(kw in lower for kw in keywords):
            return agent_name
    return "research_agent"  # safe default