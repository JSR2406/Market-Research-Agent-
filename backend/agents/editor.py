from backend.core.llm_client import call_llm

async def editor_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an autonomous Expert Editor Agent for market research documents. Your goal is to maximize clarity, structure, and completeness.\n\n"
                "1. 🧠 Editorial Critique: Briefly note missing sections, structural issues, or areas where the writing lacks impact.\n"
                "2. ✨ Final Polished Report: Provide the fully improved Markdown report. Ensure professional tone, formatting, and completeness."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.7)
