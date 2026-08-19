import logging
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

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
    
    try:
        return await call_llm(messages, temperature=0.9, max_tokens=750)
    except Exception as e:
        logger.error(f"Writer agent LLM failed: {e}")
        # Fallback to just structuring the input data into a simple report
        fallback_report = f"""# Market Research Report (Fallback Mode)

*Note: AI report generation encountered a connection or token limit error. Below is the raw structured context.*

## Summary of Findings
{task[:2500]}...

## Recommendations
- Rely on the raw data above for insights.
- Try running the query again when API limits reset.
"""
        return fallback_report
