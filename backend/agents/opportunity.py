from backend.core.llm_client import call_llm

async def opportunity_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "AI/ML product strategist. Identify 3-5 ranked product opportunities from the research. "
                "For each: Problem | Target User | AI/ML Solution | Data Needed | Business Impact. "
                "STRICTLY to the point, NO exaggeration, maximum brevity."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.3, max_tokens=400)
