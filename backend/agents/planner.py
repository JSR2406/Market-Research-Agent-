import ast
import json
import logging
import re
from typing import List, Optional

from backend.core.heuristics import fallback_plan
from backend.core.langchain_adapter import build_advisory_chain, run_prompt

logger = logging.getLogger(__name__)


# The step ids and graph nodes a plan may reference. The compiler validates
# against these, so they are the single source of truth for what a plan can say.
STRUCTURED_PLAN_PROMPT = """\
You plan advisory work for a rural micro-business. Output a JSON plan.

Return ONLY a JSON object of this exact shape, no prose, no markdown:
{"goal": "one line", "steps": [{"id":"s1","node":"research","reason":"why","tool":"web_search","pre":["topic"],"post":["findings"],"fallback":"supervisor"}]}

Allowed node values: research, analyst, schemes, writer, finalize.
Allowed tool values: web_search, scheme_match, loan_ready_score, document_checklist, cashflow_projection.
Rules:
- 3 to 5 steps. Order matters.
- "pre" = state keys that must already hold something. "post" = keys this step must produce.
- Use "post" only for: findings, analysis, schemes_text, draft, report, simplified.
- The last step must be "finalize" with post ["report","simplified"].
- "fallback" is a node to run if the postcondition fails; use "supervisor" or "finalize".
- Do not invent nodes or tools outside the allowed lists.
"""


async def structured_plan_agent(
    topic: str,
    previous_context: str = "",
) -> Optional[str]:
    """
    Ask the model for a structured plan and return the raw JSON text.

    Returns None when the model cannot produce one — the caller then falls back
    to the default topology. This is deliberately a *proposal*: the compiler
    decides whether it is usable, never the model.
    """
    context_note = ""
    if previous_context:
        context_note = (
            f"\n\nPrevious research context (build on it, do not repeat):\n"
            f"{previous_context[:600]}"
        )

    chain = build_advisory_chain(
        STRUCTURED_PLAN_PROMPT,
        agent_hint="planner",
        temperature=0.2,
        max_tokens=700,
    )
    try:
        content = await run_prompt(
            chain,
            f'Business: "{topic}".{context_note}',
            agent_hint="planner",
        )
    except Exception as e:
        logger.error(f"[Planner] structured plan failed: {e}")
        return None

    text = (content or "").strip()
    # Strip fences — models love adding them even when told not to.
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"```\s*$", "", text, flags=re.MULTILINE).strip()
    return text or None


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
    previous_context: optional summary of a prior session.

    The model is asked for a *structured* plan (see ``PLAN_SCHEMA``) and the
    caller compiles it; this function returns the prose form for the UI and the
    trace. A model that returns something unparseable is not an error — the
    compiler rejects it and the default topology runs instead.
    """
    context_note = ""
    if previous_context:
        context_note = (
            f"\n\nPrevious research context (for continuity, do not repeat — build on it):\n"
            f"{previous_context[:800]}"
        )

    chain = build_advisory_chain(
        (
            "Financial advisory planner. "
            "Output ONLY a raw Python list of exactly 5 short step strings. "
            "No explanation, no markdown."
        ),
        agent_hint=agent_hint or "planner",
        temperature=0.7,
        max_tokens=300,
    )
    try:
        content = await run_prompt(
            chain,
            (
                f'Plan the financial advisory steps needed for a rural micro-entrepreneur based on their described business: "{topic}". '
                "Cover: product/service, daily/monthly rough income, location type, whether they have any formal registration, report synthesis. "
                f'Format: ["step1","step2","step3","step4","step5"]'
                f"{context_note}"
            ),
            agent_hint=agent_hint or "planner",
        )
        return _parse_plan(content)
    except Exception as e:
        logger.error(f"Planner LLM failed: {e}")
        return fallback_plan(topic)