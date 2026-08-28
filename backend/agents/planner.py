import ast
import json
import re
from typing import List, Optional
from backend.core.llm_client import call_llm


def _parse_plan(content: str) -> List[str]:
    """Robustly extract a list of strings from LLM output."""
    content = content.strip()

    # Strip markdown fences
    content = re.sub(r"^```(?:python|json)?\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"```\s*$", "", content, flags=re.MULTILINE)
    content = content.strip()

    # Try Python literal eval (list of strings)
    try:
        result = ast.literal_eval(content)
        if isinstance(result, list) and all(isinstance(s, str) for s in result):
            return result
    except Exception:
        pass

    # Try JSON array
    try:
        result = json.loads(content)
        if isinstance(result, list):
            return [str(s) for s in result]
    except Exception:
        pass

    # Extract quoted strings as fallback
    steps = re.findall(r'"([^"]+)"', content)
    if steps:
        return steps

    # Last resort: split numbered lines
    lines = [
        re.sub(r"^\d+[\.)] \s*", "", line).strip()
        for line in content.splitlines()
        if line.strip() and re.match(r"^\d", line.strip())
    ]
    if lines:
        return lines

    raise ValueError(f"Could not parse plan from LLM output: {content[:300]}")


async def planner_agent(
    topic: str,
    previous_context: str = "",
    agent_hint: Optional[str] = "planner",
) -> List[str]:
    """
    Plan a 5-step research workflow for the given topic.
    previous_context: optional summary of a prior session (Phase 2 hook).
    """
    context_note = ""
    if previous_context:
        context_note = (
            f"\n\nPrevious research context (for continuity, do not repeat — build on it):\n"
            f"{previous_context[:800]}"
        )

    messages = [
        {
            "role": "system",
            "content": (
                "Financial advisory planner. "
                "Output ONLY a raw Python list of exactly 5 short step strings. "
                "No explanation, no markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f'Plan the financial advisory steps needed for a rural micro-entrepreneur based on their described business: "{topic}". '
                "Cover: product/service, daily/monthly rough income, location type, whether they have any formal registration, report synthesis. "
                f'Format: ["step1","step2","step3","step4","step5"]'
                f"{context_note}"
            ),
        },
    ]
    try:
        content = await call_llm(
            messages, temperature=0.7, max_tokens=300, agent_hint=agent_hint
        )
        return _parse_plan(content)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Planner LLM failed: {e}")
        return [
            f"Gather data on product/service and business model for {topic}",
            f"Analyze daily/monthly income metrics for {topic}",
            f"Research location type and operational scale for {topic}",
            f"Recommend schemes based on formal registration status and credit readiness for {topic}",
            f"Synthesize findings into a final loan readiness report for {topic}",
        ]
