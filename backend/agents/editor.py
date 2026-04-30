from backend.core.llm_client import call_llm

async def editor_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are an expert editor for market research documents. Improve structure, clarity, and completeness. Fill any missing sections. Return the improved Markdown report only — no commentary."
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.7)
