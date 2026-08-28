from typing import Optional
from backend.core.llm_client import call_llm


async def editor_agent(task: str, agent_hint: Optional[str] = "editor") -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Expert editor. You will receive a structured JSON object representing a draft "
                "financial report. "
                "Format it into polished, plain, non-jargon language (assume the reader has basic literacy). "
                "You MUST return your output STRICTLY as a JSON object with EXACTLY the following keys:\n"
                "- business_summary: string\n"
                "- cash_flow_snapshot: object (key value pairs)\n"
                "- matched_schemes: array of strings\n"
                "- documents_needed: array of strings\n"
                "- next_step: string\n"
                "Return raw JSON, no markdown blocks."
            ),
        },
        {"role": "user", "content": task},
    ]
    return await call_llm(messages, temperature=0.3, max_tokens=600, agent_hint=agent_hint)
