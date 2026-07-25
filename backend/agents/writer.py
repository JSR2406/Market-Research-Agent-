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
                "Use tables, bullet points, and headers throughout the report to make it highly readable.\n"
                "CRITICAL: You MUST include Statistical Inference and Data Visualization using Mermaid.js syntax. "
                "Embed at least two data visualizations (e.g., Pie chart for Market Share, Bar/XY chart for Market Growth/Trends) using standard Markdown code blocks with the 'mermaid' language (e.g., ```mermaid\npie title Market Share\n\"Company A\" : 40\n```)."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=1.0)
