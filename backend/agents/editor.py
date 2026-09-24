import json
import logging
from typing import Optional

from backend.core.heuristics import (
    build_heuristic_advisory,
    has_advisory_content,
    parse_advisory_json,
)
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)


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
    messages = [
        {
            "role": "system",
            "content": (
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
            ),
        },
        {"role": "user", "content": task},
    ]
    try:
        raw = await call_llm(messages, temperature=0.3, max_tokens=600, agent_hint=agent_hint)
        data = parse_advisory_json(raw)
        if data and has_advisory_content(data):
            return json.dumps(data, ensure_ascii=False)
        raise ValueError("Editor returned unusable advisory JSON")
    except Exception as e:
        logger.error(f"Editor agent LLM failed: {e}")
        return _heuristic_editor(task)