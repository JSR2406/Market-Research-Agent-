from backend.core.llm_client import call_llm

async def opportunity_agent(task: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You are an autonomous AI/ML Product Strategist Agent. Your role is to discover high-value "
                "product opportunities from market research.\n\n"
                "Structure your response as follows:\n"
                "1. 🧠 Strategic Brainstorming: Briefly outline your thought process for identifying unmet needs and why AI/ML is uniquely suited to solve them. Critique your own initial ideas.\n"
                "2. 💡 Top Opportunities: Generate 5-8 ranked product opportunities. For each opportunity, provide:\n"
                "   - **Problem**: The specific pain point.\n"
                "   - **Target User**: Who experiences this problem.\n"
                "   - **Proposed Solution**: How AI/ML solves it.\n"
                "   - **Data Needed**: What data is required to build this.\n"
                "   - **Business Impact**: Expected ROI or strategic advantage."
            )
        },
        {"role": "user", "content": task}
    ]
    return await call_llm(messages, temperature=0.9)
