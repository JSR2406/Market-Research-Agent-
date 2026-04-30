from backend.core.llm_client import call_llm

async def writer_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "You are a professional market research report writer. Write a complete Markdown report with these sections: # Executive Summary, ## Market Overview, ## Customer Segments, ## Competitive Landscape, ## Key Trends, ## AI/ML Opportunities, ## Strategic Recommendations. Use tables, bullet points, and ## headers throughout."
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=1.0)
