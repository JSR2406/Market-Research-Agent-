import ast
import json
import re
from typing import List
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
        re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        for line in content.splitlines()
        if line.strip() and re.match(r"^\d", line.strip())
    ]
    if lines:
        return lines

    raise ValueError(f"Could not parse plan from LLM output: {content[:300]}")


async def planner_agent(topic: str) -> List[str]:
    messages = [
        {
            "role": "system",
            "content": (
                "Market research planner. "
                "Output ONLY a raw Python list of exactly 5 short step strings. "
                "No explanation, no markdown."
            ),
        },
        {
            "role": "user",
            "content": (
                f'5-step research plan for: "{topic}". '
                "Cover: industry overview, customer segments, competitive landscape, "
                'AI/ML opportunities, report synthesis. Format: ["step1","step2","step3","step4","step5"]'
            ),
        },
    ]
    content = await call_llm(messages, temperature=0.7, max_tokens=300)
    return _parse_plan(content)
