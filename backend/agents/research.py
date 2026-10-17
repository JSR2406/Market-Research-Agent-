import asyncio
import logging
from datetime import datetime
from typing import Optional

from backend.core.config import WEB_SEARCH_ENABLED, WEB_SEARCH_MAX_RESULTS
from backend.core.heuristics import extract_topic, match_schemes, parse_amount, schemes_brief
from backend.core.llm_client import call_llm
from backend.core.market import live_context as market_live_context
from backend.core.web_research import web_context

logger = logging.getLogger(__name__)


def heuristic_research(task: str, market_note: str = "") -> str:
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
            if m.get("source_url"):
                lines.append(f"    (Source: {m['source_url']})")
    else:
        lines.append("No specific scheme matched — start with a MUDRA loan (collateral-free) "
                     "or a CGTMSE-backed loan from your bank.")
    lines.append("")
    lines.append("Suggested next step: register your business on Udyam (free, online), "
                 "then visit your bank with the document checklist.")
    if market_note:
        lines.append("")
        lines.append(market_note)
    return "\n".join(lines)


async def research_agent(task: str, agent_hint: Optional[str] = "research", live_context: Optional[str] = None) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    schemes_data = schemes_brief()

    user_content = f"Date: {today}.\nTask: {task}\n\nAvailable Schemes Data:\n{schemes_data}"

    # Real-time web scraping: enrich with live snippets when enabled and available.
    # `live_context` lets the agentic engine supply context it already fetched via
    # the web_search tool, so the page is never scraped twice.
    if live_context is None and WEB_SEARCH_ENABLED:
        try:
            live_context = await web_context(task, max_results=WEB_SEARCH_MAX_RESULTS)
        except Exception as e:
            logger.warning(f"[Research] Web scraping unavailable: {e}")
            live_context = ""

    if live_context:
        user_content += (
            "\n\nLive Web Context (auto-scraped — may be noisy, verify facts):\n"
            f"{live_context}"
        )

    # Live published market data (WS-8). When the topic names a commodity we have
    # a real fetched price for, it outranks a web-search estimate and is quoted
    # with the date it refers to. Empty (and free of any network call) when no
    # feed is configured or no commodity is recognised.
    market_note = ""
    try:
        market_note = await asyncio.to_thread(market_live_context, task)
    except Exception as e:  # a market feed must never break a research run
        logger.info(f"[Research] Live market data unavailable: {e}")
        market_note = ""

    if market_note:
        user_content += (
            "\n\nPublished market data (deterministic fetch — prefer this over any "
            f"web-search estimate):\n{market_note}"
        )

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
        return heuristic_research(task, market_note=market_note)