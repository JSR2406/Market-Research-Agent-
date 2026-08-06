from datetime import datetime
from backend.core.llm_client import call_llm

async def research_agent(task: str) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    messages = [
        {
            "role": "system",
            "content": (
                "Market research analyst. Provide concise, data-driven insights. "
                "Structure: Market Metrics (TAM/CAGR/key players) | Key Trends | Top Sources. "
                "Use bullet points. Be brief and factual."
            )
        },
        {
            "role": "user",
            "content": f"Date: {today}. Task: {task}"
        }
    ]
    return await call_llm(messages, temperature=0.7, max_tokens=700)
