from backend.core.llm_client import call_llm

async def analyst_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Senior market analyst. Convert research into structured insights. "
                "Include: TAM/SAM/SOM estimates, CAGR, customer segments & pain points, "
                "SWOT table, top competitor market-share figures. "
                "Use tables and bullet points. Be concise."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.6, max_tokens=750)
