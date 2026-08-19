from backend.core.llm_client import call_llm

async def analyst_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Senior market analyst. Convert research into structured insights. "
                "Include: TAM/SAM/SOM estimates, CAGR, customer segments, SWOT, top competitors. "
                "Use tables and bullet points. STRICTLY to the point, NO exaggeration, maximum brevity."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.3, max_tokens=400)
