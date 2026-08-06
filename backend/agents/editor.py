from backend.core.llm_client import call_llm

async def editor_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Expert editor. Fix gaps, improve clarity and structure. "
                "Return the polished Markdown report only. No preamble."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.6, max_tokens=600)
