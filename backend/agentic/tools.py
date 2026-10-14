"""
backend/agentic/tools.py — deterministic agent tools (zero LLM cost).

These are the tools the agentic nodes bind to and call. Every one is pure or
near-pure Python routed through the existing curated data / heuristics, so a
tool call can never invent a scheme, an amount, or a rate — matching the
project's Data & Accuracy Principles. When ``langchain`` is installed they are
also exposed as ``StructuredTool`` instances (``langchain_tools()``); otherwise
the plain registry is used by both graph runners.

Every tool can run either synchronously (``run``) or asynchronously
(``run_async``) — the agentic nodes use the async path so a slow web scrape
never blocks the WebSocket event loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgenticTool:
    name: str
    description: str
    fn: Callable[[str], str]
    tags: List[str] = field(default_factory=list)
    afn: Optional[Callable[[str], Awaitable[str]]] = None

    def run(self, tool_input: str = "") -> str:
        try:
            return self.fn(str(tool_input or ""))
        except Exception as e:  # tools must never raise into the graph
            logger.warning("[Tool:%s] failed: %s", self.name, e)
            return f"Tool {self.name} unavailable: {e}"

    async def run_async(self, tool_input: str = "") -> str:
        if self.afn is not None:
            try:
                return await self.afn(str(tool_input or ""))
            except Exception as e:
                logger.warning("[Tool:%s] async failed: %s", self.name, e)
                return f"Tool {self.name} unavailable: {e}"
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.run, str(tool_input or ""))


# ─────────────────────────────────────────────────────────────────────────────
# Tool implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _web_search_async(query: str) -> str:
    """Live web search + scrape (Google → DuckDuckGo). Records fetched sources."""
    from backend.core.web_research import web_context

    ctx = await web_context(query, max_results=3)
    return (ctx or "").strip()[:2400]


def _web_search(query: str) -> str:
    from backend.agentic.runtime import run_coro_sync

    return run_coro_sync(_web_search_async(query))


def _scheme_match(description: str) -> str:
    """Deterministic scheme matching against the curated dataset."""
    from backend.core.heuristics import extract_topic, match_schemes

    matches = match_schemes(extract_topic(description) or description, limit=4)
    return json.dumps(matches, ensure_ascii=False)


def _loan_ready_score(advisory_json: str) -> str:
    """Deterministic 0-100 loan-readiness score for an advisory JSON string."""
    from backend.core.heuristics import compute_loan_ready_score, parse_advisory_json

    data = parse_advisory_json(advisory_json)
    if data is None:
        try:
            data = json.loads(advisory_json)
        except Exception:
            data = {}
    return json.dumps(compute_loan_ready_score(data or {}), ensure_ascii=False)


def _document_checklist(description: str) -> str:
    """Deterministic document checklist derived from matched schemes."""
    from backend.core.heuristics import extract_topic, match_schemes

    base = [
        "Aadhaar card",
        "PAN card",
        "Active bank account statement (last 6 months)",
        "Two passport-size photographs",
    ]
    matches = match_schemes(extract_topic(description) or description, limit=3)
    names = " ".join(m.get("name", "") for m in matches)
    if "CGTMSE" in names or "PMEGP" in names:
        base.append("Udyam registration certificate (free, online)")
    if "SVANidhi" in names:
        base.append("Street vendor certificate / ULB identification")
    if any("MUDRA" in m.get("name", "") for m in matches):
        base.append("Proof of business activity (bills, rent receipt, or sales register)")
    return "\n".join(f"- {d}" for d in base)


def _cashflow_projection(payload: str) -> str:
    """Deterministic 12-week cash-flow projection.

    Input JSON: {"monthly_revenue": number, "weekly_expenses": number,
    "growth_per_week": 0.0-1.0 (optional), "weeks": 4-24 (optional)}.
    """
    try:
        data = json.loads(payload) if payload.strip().startswith("{") else {}
    except Exception:
        data = {}
    try:
        monthly = float(data.get("monthly_revenue", 0) or 0)
        weekly_exp = float(data.get("weekly_expenses", 0) or 0)
        growth = float(data.get("growth_per_week", 0) or 0)
        weeks = int(data.get("weeks", 12) or 12)
    except (TypeError, ValueError):
        return "Could not parse cash-flow inputs."
    if monthly <= 0:
        return "Monthly revenue not provided — ask the user for a rough monthly earning."

    weeks = max(2, min(weeks, 24))
    weekly_rev = monthly / 4.33
    rows = []
    cumulative = 0.0
    break_even = None
    for w in range(1, weeks + 1):
        rev = weekly_rev * ((1 + growth) ** (w - 1))
        surplus = rev - weekly_exp
        cumulative += surplus
        if break_even is None and cumulative > 0:
            break_even = w
        rows.append({"week": w, "revenue": round(rev), "surplus": round(surplus)})
    return json.dumps({
        "weekly_revenue_start": round(weekly_rev),
        "weekly_expenses": round(weekly_exp),
        "break_even_week": break_even,
        "monthly_surplus": round((weekly_rev - weekly_exp) * 4.33),
        "weeks": rows,
    }, ensure_ascii=False)


TOOLS: Dict[str, AgenticTool] = {
    t.name: t
    for t in [
        AgenticTool(
            "web_search",
            "Search the live web for market/loan context for a query; returns scraped snippets.",
            _web_search,
            ["research"],
            afn=_web_search_async,
        ),
        AgenticTool(
            "scheme_match",
            "Match Indian MSME government schemes to a business description (deterministic, curated).",
            _scheme_match,
            ["schemes"],
        ),
        AgenticTool(
            "loan_ready_score",
            "Compute the deterministic 0-100 loan-readiness score for an advisory JSON string.",
            _loan_ready_score,
            ["finalize"],
        ),
        AgenticTool(
            "document_checklist",
            "Deterministic bank document checklist for a business description.",
            _document_checklist,
            ["finalize", "schemes"],
        ),
        AgenticTool(
            "cashflow_projection",
            "Deterministic weekly cash-flow projection from a JSON input.",
            _cashflow_projection,
            ["analyst"],
        ),
    ]
}


def run_tool(name: str, tool_input: str = "") -> str:
    tool = TOOLS.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    return tool.run(tool_input)


async def run_tool_async(name: str, tool_input: str = "") -> str:
    tool = TOOLS.get(name)
    if tool is None:
        return f"Unknown tool: {name}"
    return await tool.run_async(tool_input)


def tool_names() -> List[str]:
    return list(TOOLS.keys())


def langchain_tools() -> List:
    """Return LangChain StructuredTool wrappers when langchain-core is present."""
    try:
        from langchain_core.tools import StructuredTool
    except Exception:
        return []

    out = []
    for name, tool in TOOLS.items():
        try:
            out.append(
                StructuredTool.from_function(
                    func=tool.run,
                    name=name,
                    description=tool.description,
                )
            )
        except Exception:  # pragma: no cover
            continue
    return out
