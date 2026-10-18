import json
import logging
from typing import Optional

from backend.core.heuristics import (
    build_heuristic_advisory,
    has_advisory_content,
    parse_advisory_json,
)
from backend.core.langchain_adapter import build_json_advisory_chain, run_prompt

logger = logging.getLogger(__name__)


EDITOR_SYSTEM = (
    "Expert editor. You will receive a structured JSON object representing a draft "
    "financial report. "
    "Format it into polished, plain, non-jargon language (assume the reader has basic literacy). "
    "You MUST return your output STRICTLY as a JSON object with EXACTLY the following keys:\n"
    "- business_summary: string\n"
    "- cash_flow_snapshot: object (key value pairs)\n"
    "- matched_schemes: array of strings\n"
    "- documents_needed: array of strings\n"
    "- next_step: string\n"
    "Return raw JSON, no markdown blocks."
)


def _heuristic_editor(task: str) -> str:
    """
    If the draft already contains a usable advisory JSON object, echo it
    normalized; otherwise build a deterministic advisory from the topic text.
    """
    data = parse_advisory_json(task)
    if data:
        return json.dumps(data, ensure_ascii=False)
    return json.dumps(build_heuristic_advisory(task), ensure_ascii=False)


async def editor_agent(task: str, agent_hint: Optional[str] = "editor") -> str:
    chain = build_json_advisory_chain(
        EDITOR_SYSTEM,
        agent_hint=agent_hint or "editor",
        temperature=0.3,
        max_tokens=600,
    )
    try:
        data = await run_prompt(
            chain,
            task,
            agent_hint=agent_hint or "editor",
        )
        if isinstance(data, dict):
            if data and has_advisory_content(data):
                return json.dumps(data, ensure_ascii=False)
            raise ValueError("Editor returned unusable advisory JSON")
        parsed = parse_advisory_json(str(data))
        if parsed and has_advisory_content(parsed):
            return json.dumps(parsed, ensure_ascii=False)
        raise ValueError("Editor returned unusable advisory JSON")
    except Exception as e:
        logger.error(f"Editor agent LLM failed: {e}")
        return _heuristic_editor(task)
