import json
import logging
import os
from datetime import datetime
from typing import Optional

from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

def load_schemes_data() -> str:
    """Load Indian MSME scheme data from local JSON."""
    file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "schemes.json")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return json.dumps(data, indent=2)
    except Exception as e:
        logger.error(f"Failed to load schemes.json: {e}")
        return "[]"

async def research_agent(task: str, agent_hint: Optional[str] = "research") -> str:
    today = datetime.now().strftime("%B %d, %Y")

    schemes_data = load_schemes_data()

    messages = [
        {
            "role": "system",
            "content": (
                "Financial research analyst. Read the provided MSME schemes data and filter "
                "facts relevant to the entrepreneur's profile described in the task. "
                "Structure: Business Profile | Relevant Schemes | Key Eligibility Facts. "
                "Use bullet points. STRICTLY to the point, NO exaggeration, maximum brevity."
            ),
        },
        {
            "role": "user",
            "content": f"Date: {today}.\nTask: {task}\n\nAvailable Schemes Data:\n{schemes_data}",
        },
    ]

    try:
        return await call_llm(messages, temperature=0.3, max_tokens=400, agent_hint=agent_hint)
    except Exception as e:
        logger.error(f"LLM call failed during research: {e}")
        fallback = (
            "### Financial Research (Fallback Mode)\n\n"
            "*Note: AI synthesis failed due to API connection issues.*\n\n"
        )
        return fallback + schemes_data
