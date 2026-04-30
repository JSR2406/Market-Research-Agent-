from backend.core.llm_client import call_llm

async def opportunity_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are an AI/ML product strategist. Generate 5-8 ranked product opportunities. For each: Problem → Target User → Proposed Solution → Data Needed → Business Impact. Format as numbered list with bold headers."
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.9)
