"""
backend/agentic/nodes.py — the agentic graph nodes.

Each node is an async ``(state, config) -> state_update`` callable (LangGraph's
node contract; the native runner calls them identically). Nodes:

    planner    → builds the research plan (wraps planner_agent)
    supervisor → decides the next action (see supervisor.py)
    research   → live web_search tool + research_agent synthesis
    analyst    → cashflow_projection tool + analyst_agent synthesis
    schemes    → scheme_match tool + opportunity_agent synthesis
    writer     → drafts the advisory JSON (writer_agent)
    critic     → self-critique / reflection (LLM, heuristic-safe)
    refine     → editor polish (editor_agent)
    finalize   → deterministic score + scheme sources + simplifier

Every node emits real-time events through the emitter in ``config`` and degrades
to the deterministic heuristic tier when the LLM is unavailable.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from backend.agentic.events import EventEmitter, WorkflowCancelled
from backend.agentic.supervisor import ACTION_TO_NODE, decide
from backend.agentic.tools import run_tool_async
from backend.agents.analyst import analyst_agent
from backend.agents.editor import editor_agent
from backend.agents.opportunity import opportunity_agent
from backend.agents.planner import planner_agent
from backend.agents.research import research_agent
from backend.agents.simplifier import simplifier_agent
from backend.agents.writer import writer_agent
from backend.core.config import AGENTIC_REFLECTION_ENABLED
from backend.core.heuristics import (
    extract_topic,
    match_schemes,
    parse_advisory_json,
    parse_amount,
)
from backend.core.llm_client import call_llm

try:  # LangGraph inspects the node signature; typing config correctly avoids a warning
    from langchain_core.runnables import RunnableConfig
except Exception:  # pragma: no cover — langchain-core absent → native runner
    RunnableConfig = dict  # type: ignore

logger = logging.getLogger(__name__)

NODE_META: Dict[str, Dict[str, str]] = {
    "planner":    {"label": "Planning",          "icon": "map"},
    "supervisor": {"label": "Supervisor",        "icon": "brain"},
    "research":   {"label": "Live Research",     "icon": "globe"},
    "analyst":    {"label": "Cash-Flow Analysis", "icon": "chart"},
    "schemes":    {"label": "Scheme Matching",   "icon": "landmark"},
    "writer":     {"label": "Report Writer",     "icon": "pencil"},
    "critic":     {"label": "Self-Critique",     "icon": "shield"},
    "refine":     {"label": "Editor",            "icon": "sparkles"},
    "finalize":   {"label": "Finalize & Simplify", "icon": "check"},
}


def _emitter(config: Optional[Dict[str, Any]]) -> EventEmitter:
    config = config or {}
    em = (config.get("configurable") or {}).get("emitter")
    if em is None:
        raise RuntimeError("agentic node called without an emitter in config")
    return em


def _check_cancel(em: EventEmitter) -> None:
    if em.is_cancelled:
        raise WorkflowCancelled()


def _summ(text: str, n: int = 180) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# ─────────────────────────────────────────────────────────────────────────────
# planner
# ─────────────────────────────────────────────────────────────────────────────

async def planner_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["planner"]
    idx = await em.node_start("planner", meta["label"], icon=meta["icon"])
    topic = state.get("topic", "")
    try:
        plan = await planner_agent(topic, previous_context=state.get("session_context", ""))
    except Exception:
        plan = []
    plan = [str(s) for s in (plan or []) if str(s).strip()][: int(state.get("max_steps", 5))]
    await em.plan(topic, plan)
    await em.node_end("planner", meta["label"], idx,
                      summary=f"{len(plan)} research steps", output="\n".join(plan))
    await em.token_usage()
    return {"plan": plan, "visited": ["planner"]}


# ─────────────────────────────────────────────────────────────────────────────
# supervisor
# ─────────────────────────────────────────────────────────────────────────────

async def supervisor_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["supervisor"]
    _check_cancel(em)
    it = int(state.get("iteration", 0)) + 1
    idx = await em.node_start("supervisor", meta["label"], iteration=it, icon=meta["icon"])
    action, reason = await decide(state)
    node = ACTION_TO_NODE.get(action, "research")
    await em.thought("supervisor", f"{_summ(reason, 140)} → next: {node}")
    await em.node_end("supervisor", meta["label"], idx,
                      summary=f"Next: {node}", output=reason, iteration=it)
    await em.token_usage()
    return {"iteration": it, "next_action": action, "visited": ["supervisor"]}


# ─────────────────────────────────────────────────────────────────────────────
# research
# ─────────────────────────────────────────────────────────────────────────────

async def research_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["research"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("research", meta["label"], iteration=it, icon=meta["icon"])
    topic = state.get("topic", "")

    await em.tool_call("research", "web_search", topic)
    live = ""
    try:
        live = await run_tool_async("web_search", topic)
    except Exception as e:
        logger.warning("[Research node] web_search failed: %s", e)
    await em.tool_result("research", "web_search",
                         summary=_summ(live, 140) or "no live pages found", ok=bool(live))

    task = (
        f"Research Topic: {topic}\n\n"
        "Your task: gather the market context, demand signals and loan-relevant "
        "facts for this micro-business."
    )
    try:
        notes = await research_agent(task, agent_hint="research", live_context=live)
    except Exception as e:
        logger.error("[Research node] research_agent failed: %s", e)
        from backend.agents.research import heuristic_research

        notes = heuristic_research(task)

    # Provenance: record only pages the web tool genuinely fetched.
    from backend.core.web_research import get_run_sources

    sink = get_run_sources()
    known = set(state.get("sources") or [])
    new_sources = [u for u in sink if u not in known]

    await em.node_end("research", meta["label"], idx,
                      summary="Gathered market & scheme facts", output=notes)
    await em.token_usage()
    return {
        "research_notes": notes,
        "findings": [{"step": "research", "agent": "research_agent", "output": notes}],
        "sources": new_sources,
        "visited": ["research"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# analyst
# ─────────────────────────────────────────────────────────────────────────────

async def analyst_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["analyst"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("analyst", meta["label"], iteration=it, icon=meta["icon"])
    topic = state.get("topic", "")

    amount = parse_amount(topic)
    projection = ""
    if amount:
        payload = json.dumps({
            "monthly_revenue": amount,
            "weekly_expenses": round(amount * 0.7 / 4.33),
            "weeks": 12,
        })
        await em.tool_call("analyst", "cashflow_projection", _summ(payload, 120))
        projection = await run_tool_async("cashflow_projection", payload)
        await em.tool_result("analyst", "cashflow_projection",
                             summary=_summ(projection, 140), ok=True)
    else:
        await em.thought("analyst", "No income figure in the description — asking for it in the report.")

    task = (
        f"Business topic: {topic}\n\n"
        f"Research notes:\n{str(state.get('research_notes', ''))[:1500]}\n\n"
        + (f"Deterministic cash-flow projection (12 weeks):\n{projection}\n\n" if projection else "")
        + "Build the structured monthly cash-flow snapshot."
    )
    try:
        analysis = await analyst_agent(task, agent_hint="analyst")
    except Exception as e:
        logger.error("[Analyst node] analyst_agent failed: %s", e)
        from backend.agents.analyst import _heuristic_analyst

        analysis = _heuristic_analyst(task)

    await em.node_end("analyst", meta["label"], idx,
                      summary="Built the cash-flow snapshot", output=analysis)
    await em.token_usage()
    return {
        "analysis": analysis,
        "findings": [{"step": "analysis", "agent": "analyst_agent", "output": analysis}],
        "visited": ["analyst"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# schemes
# ─────────────────────────────────────────────────────────────────────────────

async def schemes_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["schemes"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("schemes", meta["label"], iteration=it, icon=meta["icon"])
    topic = state.get("topic", "")

    await em.tool_call("schemes", "scheme_match", topic)
    matches_json = await run_tool_async("scheme_match", topic)
    try:
        n_matches = len(json.loads(matches_json))
    except Exception:
        n_matches = 0
    await em.tool_result("schemes", "scheme_match",
                         summary=f"{n_matches} curated scheme(s) matched", ok=True)

    task = (
        f"Business topic: {topic}\n\n"
        f"Cash-flow analysis:\n{str(state.get('analysis', ''))[:1200]}\n\n"
        f"Deterministic scheme matches (curated):\n{matches_json}\n\n"
        "Recommend 2-3 specific applicable schemes and the single most relevant next step."
    )
    try:
        schemes_text = await opportunity_agent(task, agent_hint="opportunity")
    except Exception as e:
        logger.error("[Schemes node] opportunity_agent failed: %s", e)
        from backend.agents.opportunity import _heuristic_opportunity

        schemes_text = _heuristic_opportunity(task)

    await em.node_end("schemes", meta["label"], idx,
                      summary=f"Matched {n_matches} scheme(s)", output=schemes_text)
    await em.token_usage()
    return {
        "schemes_text": schemes_text,
        "findings": [{"step": "schemes", "agent": "opportunity_agent", "output": schemes_text}],
        "visited": ["schemes"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# writer
# ─────────────────────────────────────────────────────────────────────────────

async def writer_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["writer"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("writer", meta["label"], iteration=it, icon=meta["icon"])
    topic = state.get("topic", "")
    profile = state.get("profile", "")

    combined = "\n\n---\n\n".join(
        f"### {f.get('agent', '')}\n{f.get('output', '')}" for f in (state.get("findings") or [])
    )
    writer_task = (
        f"Topic: {topic}\n"
        + (
            f"\nClient intake answers (Business Check-up):\n{profile}\n"
            "Reflect these answers inside business_summary and next_step — the "
            "advisory must be written for THIS client, not a generic one.\n"
            if profile
            else ""
        )
        + (f"\nCritic notes to address:\n{state.get('reflection')}\n" if state.get("reflection") else "")
        + f"\nAccumulated Findings:\n{combined}\n\n"
        "Write a comprehensive Loan Readiness Advisory report in the JSON schema "
        "described in your instructions."
    )

    try:
        draft = await writer_agent(writer_task, agent_hint="writer")
    except Exception as e:
        logger.error("[Writer node] writer_agent failed: %s", e)
        from backend.core.heuristics import build_heuristic_advisory

        draft = json.dumps(build_heuristic_advisory(extract_topic(topic)), ensure_ascii=False)

    await em.node_end("writer", meta["label"], idx,
                      summary="Drafted the advisory", output=_summ(draft, 400))
    await em.token_usage()
    return {"draft": draft, "visited": ["writer"]}


# ─────────────────────────────────────────────────────────────────────────────
# critic (reflection)
# ─────────────────────────────────────────────────────────────────────────────

_CRITIC_SYSTEM = (
    "You are a critical reviewer of a loan-readiness advisory for an Indian "
    "micro-entrepreneur. Review the draft JSON against the research and analysis. "
    "Look for: missing schemes, missing income figures, vague next steps, or "
    "unsupported claims. "
    'Reply ONLY as JSON: {"verdict": "pass" | "revise" | "research", "notes": "<short>"}. '
    "Use 'pass' if good, 'revise' if it just needs rewriting, 'research' if it "
    "is missing facts that must be gathered."
)


def _heuristic_critique(state: Dict) -> Dict:
    data = parse_advisory_json(state.get("draft", "")) or {}
    schemes = data.get("matched_schemes") or []
    notes = []
    if not schemes:
        notes.append("No government scheme matched.")
    if not str(data.get("business_summary", "")).strip():
        notes.append("Business summary is empty.")
    if notes:
        return {"verdict": "revise", "notes": " ".join(notes)}
    return {"verdict": "pass", "notes": "Draft looks complete."}


async def critic_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["critic"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("critic", meta["label"], iteration=it, icon=meta["icon"])

    verdict, notes = "pass", ""
    try:
        messages = [
            {"role": "system", "content": _CRITIC_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Topic: {state.get('topic', '')[:400]}\n\n"
                    f"Research:\n{str(state.get('research_notes', ''))[:1200]}\n\n"
                    f"Analysis:\n{str(state.get('analysis', ''))[:800]}\n\n"
                    f"Draft JSON:\n{state.get('draft', '')[:2500]}"
                ),
            },
        ]
        raw = await call_llm(messages, temperature=0.2, max_tokens=300, agent_hint="critic")
        obj = parse_advisory_json(raw)
        if obj is None:
            import re

            m = re.search(r"\{.*\}", raw or "", re.DOTALL)
            obj = json.loads(m.group(0)) if m else {}
        verdict = str(obj.get("verdict", "pass")).lower()
        notes = str(obj.get("notes", "")).strip()
        if verdict not in ("pass", "revise", "research"):
            verdict = "pass"
    except Exception as e:
        logger.info("[Critic node] LLM critique failed (%s) — heuristic review.", e)
        h = _heuristic_critique(state)
        verdict, notes = h["verdict"], h["notes"]

    reflected = int(state.get("reflected", 0)) + 1
    await em.reflection("critic", f"[{verdict}] {notes}", action=verdict)
    await em.node_end("critic", meta["label"], idx,
                      summary=f"Verdict: {verdict}", output=notes)
    await em.token_usage()
    return {"reflection": notes, "reflected": reflected, "critique_verdict": verdict,
            "visited": ["critic"]}


# ─────────────────────────────────────────────────────────────────────────────
# refine (editor)
# ─────────────────────────────────────────────────────────────────────────────

async def refine_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["refine"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("refine", meta["label"], iteration=it, icon=meta["icon"])

    editor_task = (
        f"Research Topic: {state.get('topic', '')}\n\n"
        f"Critic notes to address:\n{state.get('reflection') or 'none'}\n\n"
        f"Draft Report (JSON):\n{state.get('draft', '')}\n\n"
        "Polish this report from the JSON provided: fix gaps, improve clarity, "
        "ensure the JSON keys exactly match the schema described in your instructions."
    )
    try:
        report = await editor_agent(editor_task, agent_hint="editor")
    except Exception as e:
        logger.error("[Refine node] editor_agent failed: %s", e)
        report = state.get("draft", "")

    await em.node_end("refine", meta["label"], idx,
                      summary="Polished the advisory", output=_summ(report, 300))
    await em.token_usage()
    return {"report": report, "visited": ["refine"]}


# ─────────────────────────────────────────────────────────────────────────────
# finalize
# ─────────────────────────────────────────────────────────────────────────────

async def finalize_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["finalize"]
    _check_cancel(em)
    it = int(state.get("iteration", 0))
    idx = await em.node_start("finalize", meta["label"], iteration=it, icon=meta["icon"])

    report_raw = state.get("report") or state.get("draft") or ""

    # Deterministic post-pass: loan-ready score + scheme sources + provenance.
    from backend.workflows.executor import _finalize_report

    sources = list(dict.fromkeys(state.get("sources") or []))
    final_report = _finalize_report(report_raw, sources)

    # Offline / empty-draft guarantee: never emit a blank advisory.
    from backend.core.heuristics import build_heuristic_advisory, has_advisory_content

    if not has_advisory_content(parse_advisory_json(final_report) or {}):
        fallback = json.dumps(
            build_heuristic_advisory(extract_topic(state.get("topic", ""))),
            ensure_ascii=False,
        )
        final_report = _finalize_report(fallback, sources)

    await em.tool_call("finalize", "loan_ready_score", "(deterministic)")
    data = parse_advisory_json(final_report) or {}
    score = data.get("loan_ready_score", {})
    await em.tool_result("finalize", "loan_ready_score",
                         summary=f"Score {score.get('score', '?')}/100 ({score.get('level', '')})",
                         ok=True)

    await em.tool_call("finalize", "document_checklist", "(deterministic)")
    docs = data.get("documents_needed") or []
    await em.tool_result("finalize", "document_checklist",
                         summary=f"{len(docs)} document(s) listed", ok=True)

    simplified = ""
    try:
        simplified = await simplifier_agent(final_report, topic=state.get("topic", ""))
    except Exception as e:
        logger.warning("[Finalize node] simplifier failed: %s", e)

    await em.node_end("finalize", meta["label"], idx,
                      summary="Scored, sourced and simplified", output="")
    await em.token_usage()
    return {
        "report": final_report,
        "simplified": simplified,
        "loan_ready_score": score,
        "finished": True,
        "visited": ["finalize"],
    }
