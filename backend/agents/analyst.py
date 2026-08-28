from typing import Optional
from backend.core.llm_client import call_llm


async def analyst_agent(task: str, agent_hint: Optional[str] = "analyst") -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Alternative credit data analyst. Convert the entrepreneur's informal description "
                "into a structured monthly cash-flow snapshot (estimated monthly revenue, "
                "rough margin assumption, working capital need). "
                "Use tables and bullet points. STRICTLY to the point, NO exaggeration, maximum brevity."
            ),
        },
        {"role": "user", "content": task},
    ]
    return await call_llm(messages, temperature=0.3, max_tokens=450, agent_hint=agent_hint)
