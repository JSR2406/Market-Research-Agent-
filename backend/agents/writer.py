from backend.core.llm_client import call_llm

async def writer_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Market research report writer. Write a concise Markdown report with these sections: "
                "# Executive Summary | ## Market Overview | ## Customer Segments | "
                "## Competitive Landscape | ## Key Trends | ## AI/ML Opportunities | ## Strategic Recommendations. "
                "Include one mermaid pie chart (market share) and one mermaid xychart-beta (growth trend). "
                "Use bullet points and tables. Be direct."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.9, max_tokens=750)
