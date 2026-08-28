from typing import Optional
from backend.core.llm_client import call_llm


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
    return await call_llm(messages, temperature=0.3, max_tokens=350, agent_hint=agent_hint)
