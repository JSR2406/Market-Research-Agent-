from typing import Optional

from backend.core.heuristics import extract_topic, match_schemes
from backend.core.llm_client import call_llm


def _heuristic_opportunity(task: str) -> str:
    """Deterministic scheme recommendations when all LLM providers are offline."""
    matched = match_schemes(extract_topic(task), limit=3)
    lines = ["### Recommended Schemes (Offline Local Mode)", ""]
    if matched:
        for m in matched:
            lines.append(f"- **{m['name']}** — loan ceiling {m['loan_ceiling']}")
            lines.append(f"    Eligibility: {m['eligibility']}")
    else:
        lines.append("- **MUDRA (Shishu/Kishore)** — collateral-free starter loans from any bank.")
        lines.append("- **CGTMSE-backed loan** — for registered micro/small enterprises without security.")
    lines.append("")
    lines.append("**One next step:** Register your business on Udyam (free, online) if not done yet, "
                 "then visit your bank and apply with the document checklist.")
    return "\n".join(lines)


async def opportunity_agent(task: str, agent_hint: Optional[str] = "opportunity") -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Financial advisory strategist. Match the structured cash-flow snapshot and business type "
                "against Indian MSME scheme data (CGTMSE, MUDRA, PMEGP). Output 2-3 specific applicable "
                "schemes with loan ceiling and the ONE most relevant next step (e.g., 'apply for Udyam "
                "registration first, then approach a CGTMSE-empanelled bank'). "
                "STRICTLY to the point, NO exaggeration, maximum brevity."
            ),
        },
        {"role": "user", "content": task},
    ]
    try:
        return await call_llm(messages, temperature=0.3, max_tokens=350, agent_hint=agent_hint)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Opportunity LLM failed: {e}")
        return _heuristic_opportunity(task)