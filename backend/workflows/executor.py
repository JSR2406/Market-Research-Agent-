"""
executor.py — orchestrates the research workflow over a WebSocket connection.

Design:
- `reset_session_state()` clears the token counter for each fresh run.
- Every LLM call passes `agent_hint` so per-agent token budgets apply.
- `route_step()` (see workflows/routing.py) maps each plan step to an agent with
  zero LLM calls (removed the old per-step decide_agent call).
- Per-step agents (research/analyst/opportunity) accumulate findings; the
  writer + editor run ONCE at the end on all accumulated findings.
- Emits `token_usage` after every step so the frontend can show live usage.
"""
import logging

from backend.agents.analyst import analyst_agent
from backend.agents.editor import editor_agent
from backend.agents.opportunity import opportunity_agent
from backend.agents.planner import planner_agent
from backend.agents.research import research_agent
from backend.agents.simplifier import simplifier_agent
from backend.agents.writer import writer_agent
from backend.core.llm_client import SESSION_TOKEN_USAGE, reset_session_state
from backend.core.ws import SafeWebSocket
from backend.workflows.routing import AGENT_REGISTRY, SYNTHESIS_AGENTS, route_step

logger = logging.getLogger(__name__)


async def run_research_workflow(
    topic: str,
    max_steps: int,
    websocket: SafeWebSocket,
    cancel_flag: dict,
    session_context: str = "",
    session_id: str = "",
) -> None:
    """
    Main workflow. session_context is an optional string injected by ws_market.py
    when a previous session is resumed.
    """
    reset_session_state()

    await websocket.send_json({"type": "status", "message": "Planning your research..."})

    try:
        plan_steps = await planner_agent(topic, previous_context=session_context)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Planning failed: {str(e)}"})
        return

    plan_steps = plan_steps[:max_steps]
    await websocket.send_json({"type": "plan", "topic": topic, "plan": plan_steps})

    history: list[tuple[str, str, str]] = []

    for i, step in enumerate(plan_steps):
        if cancel_flag["cancelled"]:
            await websocket.send_json({"type": "cancelled"})
            return

        # Route without an LLM call.
        agent_name = route_step(step)

        # Skip writer/editor mid-pipeline; they run once at the end.
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
            for j, (_, a, r) in enumerate(history)
        )
        enriched_task = (
            f"Research Topic: {topic}\n\n"
            f"Context:\n{context if context else 'First step — no prior context.'}\n\n"
            f"Your task: {step}"
        )
        hint = agent_name.replace("_agent", "")

        agent_fn = AGENT_REGISTRY.get(agent_name, research_agent)
        try:
            output = await agent_fn(enriched_task, agent_hint=hint)
        except Exception as e:
            output = f"⚠️ Error in {agent_name}: {str(e)}"

        history.append((step, agent_name, output))

        await websocket.send_json({
            "type": "step_end",
            "step_index": i,
            "step": step,
            "agent": agent_name,
            "output": output,
        })
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
        "Write a comprehensive Loan Readiness Advisory report in the JSON schema "
        "described in your instructions."
    )

    try:
        written = await writer_agent(writer_task, agent_hint="writer")
    except Exception as e:
        written = f"⚠️ Writer error: {e}\n\n" + combined_findings[:3000]

    editor_task = (
        f"Research Topic: {topic}\n\n"
        f"Draft Report (JSON):\n{written}\n\n"
        "Polish this report from the JSON provided: fix gaps, improve clarity, "
        "ensure the JSON keys exactly match the schema described in your instructions."
    )

    try:
        final_report = await editor_agent(editor_task, agent_hint="editor")
    except Exception as e:
        final_report = written  # degrade gracefully

    # ── Simplified low-literacy document (GrameenAI use case) ─────────────────
    simplified_report = ""
    try:
        simplified_report = await simplifier_agent(final_report, topic=topic)
    except Exception as e:
        logger.warning(f"Simplifier failed, skipping simplified document: {e}")

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
        "simplified_report": simplified_report,
        "token_usage": SESSION_TOKEN_USAGE.copy(),
    })

    logger.info(f"Total token usage for this run: {SESSION_TOKEN_USAGE['total']} approx tokens")

    # Save the session when a session_id is provided.
    if session_id:
        try:
            from backend.core.memory import save_session

            state = {
                "plan": plan_steps,
                "history": history,
                "final_report": final_report,
                "simplified_report": simplified_report,
                "token_usage": SESSION_TOKEN_USAGE.copy(),
            }
            save_session(session_id, topic, state)
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")