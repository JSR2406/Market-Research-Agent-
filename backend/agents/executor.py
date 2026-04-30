import json
import re
from typing import Dict, List, Tuple
from fastapi import WebSocket
from backend.core.llm_client import call_llm
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

def _extract_json(content: str) -> Dict:
    """Robustly extract JSON from LLM output."""
    content = content.strip()
    # Strip markdown code fences
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content)
    content = content.strip()
    # Try direct parse first
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # Try finding JSON object within text
    match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
    if match:
        return json.loads(match.group())
    raise ValueError(f"Could not parse JSON from: {content[:200]}")

async def decide_agent(step: str) -> Dict[str, str]:
    prompt = f"""You are managing a market research workflow.
Given this step instruction, choose the best agent and simplify the task.
Available agents: research_agent, analyst_agent, opportunity_agent, writer_agent, editor_agent

Respond with ONLY valid JSON, no markdown, no explanation:
{{"agent": "<agent_name>", "task": "<clean task description>"}}

Step: "{step}"
"""
    content = await call_llm([{"role": "user", "content": prompt}], temperature=0.0)
    return _extract_json(content)

async def run_research_workflow(
    topic: str,
    max_steps: int,
    websocket: WebSocket,
    cancel_flag: Dict[str, bool],
) -> None:
    await websocket.send_json({"type": "status", "message": "Planning your research..."})

    try:
        plan_steps = await planner_agent(topic)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Planning failed: {str(e)}"})
        return

    plan_steps = plan_steps[:max_steps]
    await websocket.send_json({"type": "plan", "topic": topic, "plan": plan_steps})

    history: List[Tuple[str, str, str]] = []

    for i, step in enumerate(plan_steps):
        if cancel_flag["cancelled"]:
            await websocket.send_json({"type": "cancelled"})
            return

        try:
            agent_info = await decide_agent(step)
            agent_name = agent_info.get("agent", "writer_agent")
            task = agent_info.get("task", step)
            # Validate agent name
            if agent_name not in AGENT_REGISTRY:
                agent_name = "writer_agent"
        except Exception:
            agent_name = "writer_agent"
            task = step

        await websocket.send_json({
            "type": "step_start",
            "step_index": i,
            "total_steps": len(plan_steps),
            "step": step,
            "agent": agent_name,
        })

        context = "\n\n".join(
            f"### {a} (step {j+1}):\n{r}"
            for j, (s, a, r) in enumerate(history)
        )
        enriched_task = (
            f"Research Topic: {topic}\n\n"
            f"Context:\n{context if context else 'First step — no prior context.'}\n\n"
            f"Your task: {task}"
        )

        agent_fn = AGENT_REGISTRY.get(agent_name, writer_agent)
        try:
            output = await agent_fn(enriched_task)
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

    if not cancel_flag["cancelled"] and history:
        # The final report is the last agent's output (usually writer/editor)
        final_output = history[-1][2]
        await websocket.send_json({
            "type": "done",
            "topic": topic,
            "final_report": final_output,
        })
