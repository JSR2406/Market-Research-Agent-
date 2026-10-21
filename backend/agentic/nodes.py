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
from typing import Any, Dict, Optional, Tuple

from backend.agentic.events import EventEmitter, GatePaused, WorkflowCancelled
from backend.agentic.compiler import compile_plan
from backend.agentic.plan import parse_plan_json
from backend.agentic.supervisor import ACTION_TO_NODE, decide
from backend.agentic.tools import run_tool_async
from backend.agents.analyst import analyst_agent
from backend.agents.editor import editor_agent
from backend.agents.opportunity import opportunity_agent
from backend.agents.planner import planner_agent, structured_plan_agent
from backend.agents.research import research_agent
from backend.agents.simplifier import simplifier_agent
from backend.agents.writer import writer_agent
from backend.core.config import AGENTIC_REFLECTION_ENABLED, GATE_WAIT_SECONDS
from backend.core.gates import (
    DECISION_APPROVE,
    DECISION_REJECT,
    GATE_APPROVED,
    GATE_PENDING,
    GATE_REJECTED,
    build_plan_gate,
    build_scheme_gate,
    scheme_choice_from_gate,
)
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
    "gate":       {"label": "Your Approval",     "icon": "shield-check"},
    "scheme_gate": {"label": "Your Scheme Choice", "icon": "hand-coins"},
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

    # The model *proposes* a structured plan; the compiler decides whether it is
    # usable. Compilation failure is not an error — the default topology runs.
    proposed = None
    try:
        proposed = await structured_plan_agent(
            topic, previous_context=state.get("session_context", "")
        )
    except Exception as e:
        logger.warning("[Planner] structured plan unavailable: %s", e)

    compiled = None
    if proposed:
        try:
            candidate = parse_plan_json(proposed)
            compiled = compile_plan(candidate, state)
        except Exception as e:  # pragma: no cover — compiler is defensive
            logger.warning("[Planner] compilation raised: %s", e)

    if compiled is None and proposed:
        logger.info("[Planner] proposed plan rejected; using default topology")

    # Prose plan for the UI and the trace, always available.
    try:
        plan = await planner_agent(topic, previous_context=state.get("session_context", ""))
    except Exception:
        plan = []
    plan = [str(s) for s in (plan or []) if str(s).strip()][: int(state.get("max_steps", 5))]

    await em.plan(topic, plan)
    await em.node_end(
        "planner",
        meta["label"],
        idx,
        summary=(
            f"{compiled.step_count} compiled steps from a proposed plan"
            if compiled
            else f"{len(plan)} research steps (default topology)"
        ),
        output="\n".join(plan),
    )
    await em.token_usage()

    update: Dict[str, Any] = {"plan": plan, "visited": ["planner"]}
    if compiled is not None:
        # Store the serialised form only — the executor and the postcondition
        # wrapper both read state["compiled_plan"] as a plain dict.
        update["compiled_plan"] = compiled.as_dict()
    return update


# ─────────────────────────────────────────────────────────────────────────────
# gate (human approval)
# ─────────────────────────────────────────────────────────────────────────────

def _configurable(config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The `configurable` block of a LangGraph run config (never None)."""
    if not isinstance(config, dict):
        return {}
    return config.get("configurable") or {}


async def gate_node(state: Dict, config: RunnableConfig) -> Dict:
    """
    The human approval gate.

    S1 ships exactly one gate: *approve the research plan before we go to the
    web*. The payload is deterministic — the plan steps the planner proposed
    plus the eligibility families with their official source URLs — so nothing
    the model wrote can become a claim the user approves.

    Three outcomes:

    * a decision is already on the state (this run is the resumed half of a
      gate the user already answered) → honour it and move on;
    * the user approves while the run waits → the run continues;
    * nobody answers in time, or the user declines → the run parks
      (``GatePaused``) and the gate stays on disk to be decided later.
    """
    em = _emitter(config)
    meta = NODE_META["gate"]
    idx = await em.node_start("gate", meta["label"], icon=meta["icon"])
    _check_cancel(em)

    configurable = _configurable(config)
    session_id = str(configurable.get("session_id") or "")
    broker = configurable.get("gate_broker")
    lang = str(state.get("output_lang") or "en")

    # ── a decision that already exists ─────────────────────────────────────
    decision = state.get("gate_decision") or {}
    choice = str(decision.get("decision") or "")
    if choice == DECISION_REJECT:
        gate = dict(state.get("gate") or {})
        gate["status"] = GATE_REJECTED
        await em.node_end(
            "gate", meta["label"], idx,
            summary="You said no — nothing was run",
            output="",
            ok=True,
        )
        raise GatePaused(gate, status=GATE_REJECTED)
    if choice == DECISION_APPROVE:
        await em.thought("gate", "You approved this plan — continuing.")
        await em.node_end(
            "gate", meta["label"], idx,
            summary="Approved by you",
            output="",
            ok=True,
        )
        return {"gate_decision": decision, "visited": ["gate"]}

    # ── build the gate ─────────────────────────────────────────────────────
    gate = build_plan_gate(
        lang=lang,
        steps=list(state.get("plan") or []),
        schemes=list(state.get("eligibility_families") or []),
        max_steps=int(state.get("max_steps") or 4),
    )

    # Persist before we wait: a parked run must survive the socket, and the
    # decision has to be able to arrive on a later connection.
    if session_id:
        try:
            from backend.core.memory import save_session_gate

            save_session_gate(
                session_id,
                gate,
                topic=str(state.get("topic") or ""),
                intake=state.get("intake") or {},
            )
        except Exception:
            logger.warning("[Gate] could not persist the gate", exc_info=True)

    await em.gate_pending(gate)

    if broker is None:
        # No way to receive a decision on this run — park rather than block.
        await em.node_end(
            "gate", meta["label"], idx,
            summary="Waiting for your approval",
            output="",
            ok=True,
        )
        raise GatePaused(gate, status=GATE_PENDING)

    answer = await broker.wait(gate["gate_id"], GATE_WAIT_SECONDS)
    if not answer:
        # Nobody answered in time. The gate stays pending on disk; the run is
        # not approved by default and is not failed either.
        await em.node_end(
            "gate", meta["label"], idx,
            summary="Waiting for your approval",
            output="",
            ok=True,
        )
        raise GatePaused(gate, status=GATE_PENDING)

    answer = dict(answer)
    if str(answer.get("decision")) == DECISION_REJECT:
        await em.gate_decided({**gate, "status": GATE_REJECTED})
        await em.node_end(
            "gate", meta["label"], idx,
            summary="You said no — nothing was run",
            output="",
            ok=True,
        )
        raise GatePaused({**gate, "status": GATE_REJECTED}, status=GATE_REJECTED)

    await em.gate_decided({**gate, "status": GATE_APPROVED})
    await em.thought("gate", "You approved this plan — continuing.")
    await em.node_end(
        "gate", meta["label"], idx,
        summary="Approved by you",
        output="",
        ok=True,
    )
    return {"gate_decision": answer, "gate": {**gate, "status": GATE_APPROVED}, "visited": ["gate"]}


# ─────────────────────────────────────────────────────────────────────────────
# scheme_gate (human approval, second gate)
# ─────────────────────────────────────────────────────────────────────────────

async def scheme_gate_node(state: Dict, config: RunnableConfig) -> Dict:
    """
    The scheme-commitment gate.

    The plan gate asked *"may we look this up?"*. This one asks the question
    that actually costs the user something: *"which scheme shall we build the
    plan around?"* — because a written loan plan is a commitment to a loan.

    The choices are the deterministic eligibility families (eligible or likely
    only — a blocked scheme is not a decision), each carrying its official
    source URL and the date it was last verified, plus a last option for a
    user who does not want a loan right now.

    Three outcomes, exactly like the plan gate: an existing decision is
    honoured (a resumed run), an approval continues with the chosen scheme, a
    rejection or a timeout parks the run.
    """
    em = _emitter(config)
    meta = NODE_META["scheme_gate"]
    idx = await em.node_start("scheme_gate", meta["label"], icon=meta["icon"])
    _check_cancel(em)

    configurable = _configurable(config)
    session_id = str(configurable.get("session_id") or "")
    broker = configurable.get("gate_broker")
    lang = str(state.get("output_lang") or "en")

    # ── a decision that already exists ─────────────────────────────────────
    decision = dict(state.get("scheme_gate_decision") or {})
    choice_of_decision = str(decision.get("decision") or "")
    if choice_of_decision in (DECISION_APPROVE, DECISION_REJECT):
        gate = dict(state.get("scheme_gate") or {})
        if choice_of_decision == DECISION_REJECT:
            gate["status"] = GATE_REJECTED
            await em.node_end(
                "scheme_gate", meta["label"], idx,
                summary="You said no — nothing was run",
                output="",
                ok=True,
            )
            raise GatePaused(gate, status=GATE_REJECTED)
        chosen = scheme_choice_from_gate(gate, decision.get("selection"))
        await em.thought("scheme_gate", f"You chose: {chosen.get('name') or 'no loan'}.")
        await em.node_end(
            "scheme_gate", meta["label"], idx,
            summary="Approved by you",
            output="",
            ok=True,
        )
        return {
            "scheme_gate_decision": decision,
            "scheme_choice": chosen,
            "visited": ["scheme_gate"],
        }

    # ── build the gate ─────────────────────────────────────────────────────
    gate = build_scheme_gate(
        lang=lang,
        families=list(state.get("eligibility_families") or []),
        max_steps=int(state.get("max_steps") or 4),
    )

    # Nothing the user can act on → nothing to ask. The "no loan" option is
    # always present, so a gate with only that option is not worth a question.
    if len(gate.get("choices") or []) <= 1:
        await em.node_end(
            "scheme_gate", meta["label"], idx,
            summary="No scheme to choose — continuing",
            output="",
            ok=True,
        )
        return {"visited": ["scheme_gate"]}

    # Persist before we wait: a parked run must survive the socket, and the
    # decision has to be able to arrive on a later connection.
    if session_id:
        try:
            from backend.core.memory import save_session_gate

            save_session_gate(
                session_id,
                gate,
                topic=str(state.get("topic") or ""),
                intake=state.get("intake") or {},
            )
        except Exception:
            logger.warning("[Gate] could not persist the scheme gate", exc_info=True)

    await em.gate_pending(gate)

    if broker is None:
        # No way to receive a decision on this run — park rather than block.
        await em.node_end(
            "scheme_gate", meta["label"], idx,
            summary="Waiting for your choice",
            output="",
            ok=True,
        )
        raise GatePaused(gate, status=GATE_PENDING)

    answer = await broker.wait(gate["gate_id"], GATE_WAIT_SECONDS)
    if not answer:
        # Nobody answered in time. The gate stays pending on disk; the run is
        # not approved by default and is not failed either.
        await em.node_end(
            "scheme_gate", meta["label"], idx,
            summary="Waiting for your choice",
            output="",
            ok=True,
        )
        raise GatePaused(gate, status=GATE_PENDING)

    answer = dict(answer)
    if str(answer.get("decision")) == DECISION_REJECT:
        await em.gate_decided({**gate, "status": GATE_REJECTED})
        await em.node_end(
            "scheme_gate", meta["label"], idx,
            summary="You said no — nothing was run",
            output="",
            ok=True,
        )
        raise GatePaused({**gate, "status": GATE_REJECTED}, status=GATE_REJECTED)

    chosen = scheme_choice_from_gate(gate, answer.get("selection"))
    await em.gate_decided({**gate, "status": GATE_APPROVED, "selection": chosen.get("value", "")})
    await em.thought("scheme_gate", f"You chose: {chosen.get('name') or 'no loan'}.")
    await em.node_end(
        "scheme_gate", meta["label"], idx,
        summary="Approved by you",
        output="",
        ok=True,
    )
    return {
        "scheme_gate_decision": answer,
        "scheme_choice": chosen,
        "visited": ["scheme_gate"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# supervisor
# ─────────────────────────────────────────────────────────────────────────────

async def supervisor_node(state: Dict, config: RunnableConfig) -> Dict:
    em = _emitter(config)
    meta = NODE_META["supervisor"]
    _check_cancel(em)
    it = int(state.get("iteration", 0)) + 1
    idx = await em.node_start("supervisor", meta["label"], iteration=it, icon=meta["icon"])

    # A compiled plan, when present, is the routing decision. The supervisor
    # still checks preconditions and can skip a step, but it no longer invents
    # the order — the compiler already validated it.
    compiled = state.get("compiled_plan")
    action, reason = await _decide_with_plan(state, compiled)

    node = ACTION_TO_NODE.get(action, "research")
    await em.thought("supervisor", f"{_summ(reason, 140)} → next: {node}")
    await em.node_end("supervisor", meta["label"], idx,
                      summary=f"Next: {node}", output=reason, iteration=it)
    await em.token_usage()
    return {"iteration": it, "next_action": action, "visited": ["supervisor"]}


async def _decide_with_plan(
    state: Dict, compiled: Optional[Dict]
) -> Tuple[str, str]:
    """
    Pick the next action.

    With a compiled plan: take the first step whose preconditions hold and which
    has not already run. With no plan: the heuristic supervisor decides, exactly
    as before — so a rejected plan costs the user nothing.
    """
    if not compiled:
        return await decide(state)

    steps = compiled.get("steps") or []
    visited = {str(v) for v in (state.get("visited") or [])}

    for step in steps:
        node = str(step.get("node") or "")
        if node in visited:
            continue
        pre = [str(k) for k in (step.get("pre") or [])]
        missing = [k for k in pre if state.get(k) in (None, "", [], {}, 0)]
        if missing:
            # Preconditions unmet — skip this step and try the next one rather
            # than running work that cannot succeed.
            continue
        return node, f"planned step {step.get('id')}: {step.get('reason') or node}"

    # Every planned step has run (or been skipped). Fall back to the heuristic so
    # the graph can still close out through writer/finalize.
    return await decide(state)


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

def _scheme_choice_block(choice: Dict[str, Any]) -> str:
    """
    The user's scheme decision, as an instruction the writer cannot ignore.

    The eligibility note says what the rule engine found; this says what the
    *user* chose. It overrides the prose the model would otherwise write: the
    report is built around the approved scheme, and never around a different
    one the model happens to like better.
    """
    if not isinstance(choice, dict) or not choice:
        return ""
    if choice.get("is_none"):
        return (
            "THE USER DECLINED A LOAN (they chose the option 'no loan right "
            "now'). Write the plan around growing the business with what they "
            "already have. You may mention a government scheme in passing, but "
            "you must NOT present any scheme as the recommended route, and you "
            "must not build a repayment plan for one."
        )
    name = str(choice.get("name") or "").strip()
    if not name:
        return ""
    ceiling = str(choice.get("loan_ceiling") or "").strip()
    source = str(choice.get("source_url") or "").strip()
    parts = [
        f"THE USER APPROVED THIS SCHEME: {name}.",
        "Build the whole report around this scheme — the documents, the steps "
        "and the repayment plan must be for THIS scheme.",
        "Do not recommend a different scheme as the main path. You may list "
        "other schemes as alternatives, clearly marked as not chosen.",
    ]
    if ceiling:
        parts.append(f"The approved scheme's amount: {ceiling}.")
    if source:
        parts.append(f"Official source for this scheme: {source}.")
    return " ".join(parts)


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
    eligibility_note = state.get("eligibility_note", "")
    output_lang = state.get("output_lang", "en")
    choice = state.get("scheme_choice") or {}
    choice_block = _scheme_choice_block(choice)
    lang_rule = (
        "Write the ENTIRE advisory in simple, plain Hindi (Devanagari script). "
        "Keep scheme names, loan amounts and official terms (Udyam, GST, MUDRA, "
        "PM SVANidhi, CGTMSE, PMEGP) in English — the user must recognise them on a "
        "bank form. The JSON keys stay in English."
        if output_lang == "hi"
        else "Write the ENTIRE advisory in simple, plain English."
    )
    writer_task = (
        f"Topic: {topic}\n"
        + (
            f"\nClient intake answers (Business Check-up):\n{profile}\n"
            "Reflect these answers inside business_summary and next_step - the "
            "advisory must be written for THIS client, not a generic one.\n"
            if profile
            else ""
        )
        + (
            f"\nDETERMINISTIC ELIGIBILITY VERDICTS (computed in code - these "
            f"override anything you might infer, and you must not contradict them):\n"
            f"{eligibility_note}\n"
            if eligibility_note
            else ""
        )
        + (f"\nCritic notes to address:\n{state.get('reflection')}\n" if state.get("reflection") else "")
        + (f"\n{choice_block}\n" if choice_block else "")
        + f"\nAccumulated Findings:\n{combined}\n\n"
        f"{lang_rule} "
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
    choice_block = _scheme_choice_block(state.get("scheme_choice") or {})
    try:
        messages = [
            {"role": "system", "content": _CRITIC_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Topic: {state.get('topic', '')[:400]}\n\n"
                    f"Research:\n{str(state.get('research_notes', ''))[:1200]}\n\n"
                    f"Analysis:\n{str(state.get('analysis', ''))[:800]}\n\n"
                    + (f"{choice_block}\n\n" if choice_block else "")
                    + f"Draft JSON:\n{state.get('draft', '')[:2500]}"
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

    editor_lang = (
        "Keep the report in simple Hindi (Devanagari script), with scheme names "
        "and amounts in English."
        if state.get("output_lang", "en") == "hi"
        else "Keep the report in simple English."
    )
    editor_task = (
        f"Research Topic: {state.get('topic', '')}\n\n"
        f"Critic notes to address:\n{state.get('reflection') or 'none'}\n\n"
        + (f"{_scheme_choice_block(state.get('scheme_choice') or {})}\n\n"
           if state.get("scheme_choice") else "")
        + f"Draft Report (JSON):\n{state.get('draft', '')}\n\n"
        f"{editor_lang} "
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
    final_report = _finalize_report(
        report_raw, sources, scheme_choice=state.get("scheme_choice") or {},
    )

    # Offline / empty-draft guarantee: never emit a blank advisory.
    from backend.core.heuristics import build_heuristic_advisory, has_advisory_content

    if not has_advisory_content(parse_advisory_json(final_report) or {}):
        fallback = json.dumps(
            build_heuristic_advisory(extract_topic(state.get("topic", ""))),
            ensure_ascii=False,
        )
        final_report = _finalize_report(
            fallback, sources, scheme_choice=state.get("scheme_choice") or {},
        )

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
        simplified = await simplifier_agent(
            final_report,
            topic=state.get("topic", ""),
            lang=state.get("output_lang", "en"),
        )
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
