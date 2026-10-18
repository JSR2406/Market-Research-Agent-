from typing import Optional

from backend.core.heuristics import extract_topic, parse_amount
from backend.core.langchain_adapter import build_advisory_chain, run_prompt


def _heuristic_analyst(task: str) -> str:
    """Deterministic cash-flow snapshot when all LLM providers are offline."""
    amount = parse_amount(extract_topic(task))
    if not amount:
        return (
            "### Cash-Flow Snapshot\n\n"
            "Add your rough monthly earnings (e.g. 'I earn about ₹15,000 per month') "
            "in the description to get an automated cash-flow estimate."
        )
    working_capital = min(amount, 50_000)
    return (
        "### Cash-Flow Snapshot (Offline Estimate)\n\n"
        "| Metric | Estimate |\n"
        "|---|---|\n"
        f"| Estimated monthly revenue | ₹{amount:,} |\n"
        f"| Assumed rough margin (~30%) | ₹{int(amount * 0.3):,} |\n"
        f"| Indicative working capital need | ₹{working_capital:,} |\n\n"
        "*Generated from local data — AI providers were unavailable. Confirm with real numbers at your bank.*"
    )


async def analyst_agent(task: str, agent_hint: Optional[str] = "analyst") -> str:
    chain = build_advisory_chain(
        (
            "Alternative credit data analyst. Convert the entrepreneur's informal description "
            "into a structured monthly cash-flow snapshot (estimated monthly revenue, "
            "rough margin assumption, working capital need). "
            "Use tables and bullet points. STRICTLY to the point, NO exaggeration, maximum brevity."
        ),
        agent_hint=agent_hint or "analyst",
        temperature=0.3,
        max_tokens=450,
    )
    try:
        return await run_prompt(
            chain,
            task,
            agent_hint=agent_hint or "analyst",
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Analyst LLM failed: {e}")
        return _heuristic_analyst(task)