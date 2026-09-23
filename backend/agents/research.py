import logging
from datetime import datetime
from typing import Optional

from backend.core.config import WEB_SEARCH_ENABLED, WEB_SEARCH_MAX_RESULTS
from backend.core.heuristics import extract_topic, match_schemes, parse_amount, schemes_json
from backend.core.llm_client import call_llm
from backend.core.web_research import web_context

logger = logging.getLogger(__name__)


def heuristic_research(task: str) -> str:
    """
    Deterministic fallback for the research agent: keyword-match the local MSME
    scheme dataset. Guarantees a useful answer when all LLM providers are offline.
    """
    topic = extract_topic(task)
    matched = match_schemes(topic, limit=3)
    amount = parse_amount(topic)
    lines = [
        "### Financial Research (Offline Local Mode)",
        "",
        "*Note: AI providers were unavailable; this output comes from local government scheme data only.*",
        "",
    ]
    if amount:
        lines.append(f"Estimated monthly income found in the description: ₹{amount:,}.")
    if matched:
        lines.append("Relevant schemes (keyword match from your profile):")
        for m in matched:
            lines.append(f"- {m['name']} | loan ceiling {m['loan_ceiling']}")
            lines.append(f"    Eligibility: {m['eligibility']}")
    else:
        lines.append("No specific scheme matched — start with a MUDRA loan (collateral-free) "
                     "or a CGTMSE-backed loan from your bank.")
    lines.append("")
    lines.append("Suggested next step: register your business on Udyam (free, online), "
                 "then visit your bank with the document checklist.")
    return "\n".join(lines)


async def research_agent(task: str, agent_hint: Optional[str] = "research") -> str:
    today = datetime.now().strftime("%B %d, %Y")
    schemes_data = schemes_json()

    user_content = f"Date: {today}.\nTask: {task}\n\nAvailable Schemes Data:\n{schemes_data}"

    # Real-time web scraping: enrich with live snippets when enabled and available.
    if WEB_SEARCH_ENABLED:
        try:
            live = await web_context(task, max_results=WEB_SEARCH_MAX_RESULTS)
            if live:
                user_content += (
                    "\n\nLive Web Context (auto-scraped — may be noisy, verify facts):\n"
                    f"{live}"
                )
        except Exception as e:
            logger.warning(f"[Research] Web scraping unavailable: {e}")

    messages = [
        {
            "role": "system",
            "content": (
                "Financial research analyst. Read the provided MSME schemes data and "
                "filter facts relevant to the entrepreneur's profile described in the "
                "task. Use the Live Web Context only to confirm or correct scheme "
                "details — never invent figures. "
                "Structure: Business Profile | Relevant Schemes | Key Eligibility Facts. "
                "Use bullet points. STRICTLY to the point, NO exaggeration, maximum brevity."
            ),
        },
        {"role": "user", "content": user_content},
    ]

    try:
        return await call_llm(messages, temperature=0.3, max_tokens=400, agent_hint=agent_hint)
    except Exception as e:
        logger.error(f"LLM call failed during research: {e}")
        return heuristic_research(task)