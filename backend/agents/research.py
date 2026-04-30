from datetime import datetime
from backend.core.llm_client import call_llm

async def research_agent(task: str) -> str:
    today = datetime.now().strftime("%B %d, %Y")
    messages = [
        {
            "role": "system",
            "content": "You are a real-time market research specialist. Return bullet points with source names in parentheses. Focus on data from the last 12 months. Include market sizes, growth rates, and key players."
        },
        {
            "role": "user",
            "content": f"Today is {today}.\n\nResearch task: {task}"
        }
    ]
    return await call_llm(messages, temperature=0.7)
