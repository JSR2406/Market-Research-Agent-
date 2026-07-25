from datetime import datetime
from backend.core.llm_client import call_llm

async def research_agent(task: str) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    messages = [
        {
            "role": "system",
            "content": (
                "You are an autonomous Market Research Agent. Your goal is to deeply analyze "
                "the given task and provide highly accurate, data-driven insights. "
                "Before answering, you must internally reason about the task using this structure:\n\n"
                "1. 🧠 Autonomous Thought Process: Break down the task, identify what specific market metrics "
                "(TAM, CAGR, key players, trends) you need to deduce, and critically evaluate the context.\n"
                "2. 🔎 Simulated Search Queries: List 2-3 targeted web search queries you would logically run to "
                "find this data for the last 12 months.\n"
                "3. 📊 Market Analysis: The core research findings based on your synthesis. Use clear bullet points.\n"
                "4. 🔗 Sources: List the deduced or expected reputable sources (in parentheses) for these metrics."
            )
        },
        {
            "role": "user",
            "content": f"Today is {today}.\n\nContext and Research task: {task}"
        }
    ]
    return await call_llm(messages, temperature=0.7)
