from backend.core.llm_client import call_llm

async def editor_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Expert editor. Fix gaps, improve clarity. "
                "Return the polished Markdown report only. No preamble. "
                "STRICTLY to the point, NO exaggeration, maximum brevity."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.3, max_tokens=450)
