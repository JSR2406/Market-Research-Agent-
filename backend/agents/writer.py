from backend.core.llm_client import call_llm

async def writer_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an autonomous professional Market Research Report Writer Agent.\n\n"
                "Before drafting the report, you must structure your thinking:\n"
                "1. 🧠 Narrative Planning: Briefly outline the core narrative, key themes, and flow of the report based on the provided context.\n"
                "2. 📝 Full Report: Write a complete Markdown report with these sections:\n"
                "   # Executive Summary\n"
                "   ## Market Overview\n"
                "   ## Customer Segments\n"
                "   ## Competitive Landscape\n"
                "   ## Key Trends\n"
                "   ## AI/ML Opportunities\n"
                "   ## Strategic Recommendations\n"
                "Use tables, bullet points, and headers throughout the report to make it highly readable."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=1.0)
