"""
backend/agentic/state.py — the shared graph state for the agentic advisory engine.

The state is a ``TypedDict`` so it can be handed to a LangGraph ``StateGraph``
directly, and the list fields use ``operator.add`` reducers so concurrent /
sequential node updates *append* instead of overwriting. The exact same state
shape is consumed by the built-in native runner (see runner.py), so behaviour is
identical whether or not ``langgraph`` is installed.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class TraceEntry(TypedDict, total=False):
    """One line in the agentic trace surfaced to the UI (thoughts, tools, ...)."""

    node: str
    kind: str  # "thought" | "tool_call" | "tool_result" | "reflection" | "note" | "plan"
    text: str
    tool: str
    input: str
    ok: bool


class AgenticState(TypedDict, total=False):
    # ── inputs ──────────────────────────────────────────────────────────────
    topic: str
    profile: str
    session_context: str
    max_steps: int
    # Deterministic verdicts computed in code before any LLM runs — the writer
    # is told these so the prose can never contradict the rule engine.
    eligibility_note: str
    # The same verdicts as structured data (name, status, source url) so a
    # human-facing surface — the approval gate — can show them with their
    # provenance instead of a prose blob.
    eligibility_families: List[Dict[str, Any]]
    # Language the whole advisory must be written in, set from the UI language.
    output_lang: str
    # The Business Check-up answers, carried into the run so a parked gate can
    # be resumed with the same intake (the eligibility verdicts depend on it).
    intake: Dict[str, str]

    # ── approval gates ──────────────────────────────────────────────────────
    gate: Dict[str, Any]           # the plan gate record (pending or decided)
    gate_decision: Dict[str, Any]  # a decision injected into a resumed run
    # The scheme gate: the second gate in the chain, where the user picks the
    # scheme the advisory is built around.
    scheme_gate: Dict[str, Any]
    scheme_gate_decision: Dict[str, Any]
    # What the user chose — the writer must build the report around exactly
    # this and may not recommend a different scheme as the main path.
    scheme_choice: Dict[str, Any]

    # ── planning ────────────────────────────────────────────────────────────
    plan: Annotated[List[str], operator.add]
    iteration: int            # supervisor hops (bounded by AGENTIC_MAX_ITERATIONS)

    # ── accumulated work ────────────────────────────────────────────────────
    findings: Annotated[List[Dict[str, str]], operator.add]
    sources: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]
    trace: Annotated[List[TraceEntry], operator.add]
    visited: Annotated[List[str], operator.add]

    research_notes: str
    analysis: str
    schemes_text: str
    draft: str                # writer's advisory JSON (pre-editor)
    reflection: str           # critic's review notes
    reflected: int            # how many critique passes have run

    # ── output ──────────────────────────────────────────────────────────────
    report: str               # finalized advisory JSON (string)
    simplified: str           # low-literacy plain-language document
    loan_ready_score: Dict[str, Any]

    # ── control ─────────────────────────────────────────────────────────────
    next_action: str
    finished: bool


def initial_state(
    topic: str,
    max_steps: int,
    profile: str = "",
    session_context: str = "",
    eligibility_note: str = "",
    *,
    intake: Optional[Dict[str, str]] = None,
    eligibility_families: Optional[List[Dict[str, Any]]] = None,
    gate: Optional[Dict[str, Any]] = None,
    gate_decision: Optional[Dict[str, Any]] = None,
    scheme_gate: Optional[Dict[str, Any]] = None,
    scheme_gate_decision: Optional[Dict[str, Any]] = None,
    scheme_choice: Optional[Dict[str, Any]] = None,
) -> AgenticState:
    """Fresh state for one advisory run."""
    return AgenticState(
        topic=topic,
        profile=profile,
        session_context=session_context,
        eligibility_note=eligibility_note,
        eligibility_families=list(eligibility_families or []),
        intake=dict(intake or {}),
        gate=dict(gate or {}),
        gate_decision=dict(gate_decision or {}),
        scheme_gate=dict(scheme_gate or {}),
        scheme_gate_decision=dict(scheme_gate_decision or {}),
        scheme_choice=dict(scheme_choice or {}),
        output_lang="en",
        max_steps=max(1, min(int(max_steps or 5), 6)),
        plan=[],
        iteration=0,
        findings=[],
        sources=[],
        errors=[],
        trace=[],
        visited=[],
        research_notes="",
        analysis="",
        schemes_text="",
        draft="",
        reflection="",
        reflected=0,
        report="",
        simplified="",
        loan_ready_score={},
        next_action="",
        finished=False,
    )
