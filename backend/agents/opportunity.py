from backend.core.llm_client import call_llm

async def opportunity_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "AI/ML product strategist. Identify 5 ranked product opportunities from the research. "
                "For each: Problem | Target User | AI/ML Solution | Data Needed | Business Impact. "
                "Be concise and specific."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.8, max_tokens=700)
