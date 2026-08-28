"""
executor.py — Phase 1c changes
- Call reset_session_state() at the start of each workflow run (clears cache + token counter)
- Pass agent_hint to every agent call so per-agent token budgets apply
- Eliminate the decide_agent LLM call per step: use a simple keyword-matching router instead
  (saves 1 LLM call per step, i.e. up to 6 fewer calls for max_steps=6)
- Emit token_usage WebSocket events after each step so the frontend can show live usage
- Final writer+editor pass: run them once at the end on the accumulated findings (not per-step)
  when the plan has ≥2 steps (avoids redundant re-synthesis on every step)
"""
import json
import re
from typing import Dict, List, Tuple

from fastapi import WebSocket

from backend.core.llm_client import call_llm, reset_session_state, SESSION_TOKEN_USAGE
from backend.agents.planner import planner_agent
from backend.agents.research import research_agent
from backend.agents.analyst import analyst_agent
from backend.agents.opportunity import opportunity_agent
from backend.agents.writer import writer_agent
from backend.agents.editor import editor_agent

AGENT_REGISTRY = {
    "research_agent": research_agent,
    "analyst_agent": analyst_agent,
    "opportunity_agent": opportunity_agent,
    "writer_agent": writer_agent,
    "editor_agent": editor_agent,
}

# ── Step-to-agent router (keyword matching, zero LLM calls) ───────────────────
# Replaces the old decide_agent() which fired a full LLM call per step.
_ROUTING_RULES: List[Tuple[List[str], str]] = [
    (["research", "scrape", "gather", "data", "source", "find", "retrieve"], "research_agent"),
    (["analys", "metric", "tam", "sam", "cagr", "swot", "segment", "competitor"], "analyst_agent"),
    (["opportunit", "ai/ml", "product", "solution", "strateg", "recommend"], "opportunity_agent"),
    (["write", "draft", "report", "synthesize", "compile", "summarize"], "writer_agent"),
    (["edit", "polish", "refine", "review", "improve", "finalize"], "editor_agent"),
]


def _route_step(step: str) -> str:
    """Map a plan step string to an agent name using keyword matching."""
    lower = step.lower()
    for keywords, agent_name in _ROUTING_RULES:
        if any(kw in lower for kw in keywords):
            return agent_name
    return "research_agent"  # safe default


def _extract_json(content: str) -> Dict:
    """Robustly extract JSON from LLM output, including nested objects."""
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE)
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    depth = 0
    start = None
    for idx, ch in enumerate(content):
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = content[start: idx + 1]
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    start = None

    raise ValueError(f"Could not parse JSON from LLM output: {content[:300]}")


async def run_research_workflow(
    topic: str,
    max_steps: int,
    websocket: WebSocket,
    cancel_flag: Dict[str, bool],
    session_context: str = "",
    session_id: str = "",
) -> None:
    """
    Main workflow. session_context is an optional string injected by ws_market.py
    when a previous session is resumed (Phase 2 hook — no-op if empty in Phase 1).
    """
    # Phase 1b: reset cache + token counter for each fresh run
    reset_session_state()

    await websocket.send_json({"type": "status", "message": "Planning your research..."})

    try:
        plan_steps = await planner_agent(topic, previous_context=session_context)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Planning failed: {str(e)}"})
        return

    plan_steps = plan_steps[:max_steps]
    await websocket.send_json({"type": "plan", "topic": topic, "plan": plan_steps})

    # Separate research/analysis steps from synthesis steps
    # Strategy: run research_agent/analyst_agent/opportunity_agent per step (they are cheap),
    # then do ONE writer+editor pass at the very end on all accumulated findings.
    # This avoids writer/editor firing redundantly on every step.
    SYNTHESIS_AGENTS = {"writer_agent", "editor_agent"}

    history: List[Tuple[str, str, str]] = []
    research_findings: List[str] = []

    for i, step in enumerate(plan_steps):
        if cancel_flag["cancelled"]:
            await websocket.send_json({"type": "cancelled"})
            return

        # Route without LLM call (Phase 1c: eliminate decide_agent cost)
        agent_name = _route_step(step)

        # Skip writer/editor mid-pipeline; we'll run them once at the end
        if agent_name in SYNTHESIS_AGENTS:
            agent_name = "research_agent"

        await websocket.send_json({
            "type": "step_start",
            "step_index": i,
            "total_steps": len(plan_steps),
            "step": step,
            "agent": agent_name,
        })

        context = "\n\n".join(
            f"### {a} (step {j + 1}):\n{r}"
            for j, (s, a, r) in enumerate(history)
        )
        enriched_task = (
            f"Research Topic: {topic}\n\n"
            f"Context:\n{context if context else 'First step — no prior context.'}\n\n"
            f"Your task: {step}"
        )

        # Derive agent_hint from agent name for token budgeting
        hint = agent_name.replace("_agent", "")

        agent_fn = AGENT_REGISTRY.get(agent_name, research_agent)
        try:
            output = await agent_fn(enriched_task, agent_hint=hint)
        except Exception as e:
            output = f"⚠️ Error in {agent_name}: {str(e)}"

        history.append((step, agent_name, output))
        research_findings.append(output)

        await websocket.send_json({
            "type": "step_end",
            "step_index": i,
            "step": step,
            "agent": agent_name,
            "output": output,
        })

        # Emit token usage after every step (Phase 1b)
        await websocket.send_json({
            "type": "token_usage",
            "input_tokens": SESSION_TOKEN_USAGE["input"],
            "output_tokens": SESSION_TOKEN_USAGE["output"],
            "total_tokens": SESSION_TOKEN_USAGE["total"],
        })

    if cancel_flag["cancelled"]:
        await websocket.send_json({"type": "cancelled"})
        return

    # ── Final synthesis pass (writer → editor) — runs ONCE ───────────────────
    if not history:
        return

    await websocket.send_json({"type": "status", "message": "Writing final report..."})

    combined_findings = "\n\n---\n\n".join(
        f"### Step {i+1}: {s}\n{r}"
        for i, (s, _, r) in enumerate(history)
    )
    writer_task = (
        f"Topic: {topic}\n\n"
        f"Accumulated Findings:\n{combined_findings}\n\n"
        "Write a comprehensive Loan Readiness Advisory report in Markdown."
    )

    try:
        written = await writer_agent(writer_task, agent_hint="writer")
    except Exception as e:
        written = f"⚠️ Writer error: {e}\n\n" + combined_findings[:3000]

    editor_task = (
        f"Research Topic: {topic}\n\n"
        f"Draft Report (JSON):\n{written}\n\n"
        "Polish this report from the JSON provided: fix gaps, improve clarity, ensure Markdown is well-structured."
    )

    try:
        final_report = await editor_agent(editor_task, agent_hint="editor")
    except Exception as e:
        final_report = written  # degrade gracefully

    await websocket.send_json({
        "type": "token_usage",
        "input_tokens": SESSION_TOKEN_USAGE["input"],
        "output_tokens": SESSION_TOKEN_USAGE["output"],
        "total_tokens": SESSION_TOKEN_USAGE["total"],
    })

    await websocket.send_json({
        "type": "done",
        "topic": topic,
        "final_report": final_report,
        "token_usage": SESSION_TOKEN_USAGE.copy(),
    })

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Total token usage for this run: {SESSION_TOKEN_USAGE['total']} approx tokens")

    # Phase 2 hook: save session on completion
    if session_id:
        try:
            from backend.core.memory import save_session
            state = {
                "plan": plan_steps,
                "history": history,
                "final_report": final_report,
                "token_usage": SESSION_TOKEN_USAGE.copy(),
            }
            save_session(session_id, topic, state)
        except ImportError:
            pass  # memory module not available
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save session {session_id}: {e}")

