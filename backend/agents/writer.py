import json
import logging
from typing import Optional

from backend.core.heuristics import (
    build_heuristic_advisory,
    extract_topic,
    has_advisory_content,
    parse_advisory_json,
)
from backend.core.langchain_adapter import build_json_advisory_chain, run_prompt

logger = logging.getLogger(__name__)


WRITER_SYSTEM = (
    "Financial report writer. You MUST return your output STRICTLY as a JSON object "
    "with EXACTLY the following keys:\n"
    "- business_summary: string\n"
    "- cash_flow_snapshot: object\n"
    "- matched_schemes: array of strings\n"
    "- documents_needed: array of strings\n"
    "- next_step: string\n"
    "Return raw JSON, no markdown blocks."
)


async def writer_agent(task: str, agent_hint: Optional[str] = "writer") -> str:
    chain = build_json_advisory_chain(
        WRITER_SYSTEM,
        agent_hint=agent_hint or "writer",
        temperature=0.4,
        max_tokens=600,
    )
    try:
        data = await run_prompt(
            chain,
            task,
            agent_hint=agent_hint or "writer",
        )
        # run_prompt with JsonOutputParser returns a dict; serialise back to JSON string
        if isinstance(data, dict):
            if has_advisory_content(data):
                return json.dumps(data, ensure_ascii=False)
            raise ValueError("Writer returned unusable advisory JSON")
        parsed = parse_advisory_json(str(data))
        if parsed and has_advisory_content(parsed):
            return json.dumps(parsed, ensure_ascii=False)
        raise ValueError("Writer returned unusable advisory JSON")
    except Exception as e:
        logger.error(f"Writer agent LLM failed: {e}")
        return json.dumps(
            build_heuristic_advisory(extract_topic(task)), ensure_ascii=False
        )
