from backend.core.llm_client import call_llm

async def analyst_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a senior market analyst. Convert research into structured insights: TAM/SAM/SOM estimates, growth rates, customer segments, pain points, and SWOT analysis. Use tables and bullet points."
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.6)
