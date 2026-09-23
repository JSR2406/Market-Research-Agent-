import json
import logging
from typing import Optional

from backend.core.heuristics import build_simplified_summary
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)


async def simplifier_agent(
    advisory_json: str,
    topic: str = "",
    agent_hint: Optional[str] = "simplifier",
) -> str:
    """
    Convert a finalized advisory JSON into a low-literacy, print-friendly plain
    document. Short numbered lines, no jargon — readable aloud to a first-time
    borrower. Falls back to a deterministic summary when the LLM is unavailable.
    """
    messages = [
        {
            "role": "system",
            "content": (
                "You write for a first-time borrower with basic literacy. Convert the "
                "advisory JSON into a short plain-language document: 4-6 numbered lines, "
                "very simple words, no jargon, no abbreviations like CGTMSE/marginal. "
                "Return plain text only — no markdown, no JSON."
            ),
        },
        {
            "role": "user",
            "content": f"Topic: {topic}\n\nAdvisory JSON:\n{advisory_json}",
        },
    ]
    try:
        return await call_llm(
            messages, temperature=0.3, max_tokens=200, agent_hint=agent_hint
        )
    except Exception as e:
        logger.error(f"Simplifier agent LLM failed: {e}")
        try:
            data = json.loads(advisory_json)
        except json.JSONDecodeError:
            data = {}
        return build_simplified_summary(data, topic)