import json
import logging
from typing import Optional

from backend.core.heuristics import build_heuristic_advisory, extract_topic
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)


async def writer_agent(task: str, agent_hint: Optional[str] = "writer") -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Financial report writer. You MUST return your output STRICTLY as a JSON object "
                "with EXACTLY the following keys:\n"
                "- business_summary: string\n"
                "- cash_flow_snapshot: object\n"
                "- matched_schemes: array of strings\n"
                "- documents_needed: array of strings\n"
                "- next_step: string\n"
                "Do not include Markdown blocks like ```json in the output, just raw JSON."
            ),
        },
        {"role": "user", "content": task},
    ]
    try:
        return await call_llm(messages, temperature=0.4, max_tokens=600, agent_hint=agent_hint)
    except Exception as e:
        logger.error(f"Writer agent LLM failed: {e}")
        return json.dumps(
            build_heuristic_advisory(extract_topic(task)), ensure_ascii=False
        )