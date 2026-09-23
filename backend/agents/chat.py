"""
chat.py — specialised business-advisory & business-building chat agent.

Scope (stays on-topic):
  1. Building businesses — turning an idea into a viable small business: model,
     pricing, costs, cash flow, customers, registration (Udyam/GST), money habits.
  2. Loan-readiness advisory — matching curated schemes, eligibility, documents
     and "what to say at the bank".

Every turn carries recent chat memory + the session's latest advisory (when
available). Falls back to a deterministic heuristic reply when all LLM
providers are unreachable — it never crashes, never returns empty.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from backend.core.heuristics import match_schemes, schemes_json
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

_SCHEMES_EXCERPT = schemes_json()[:1500]

SYSTEM_PROMPT = (
    "You are GrameenAI, a specialised business advisor and business builder for "
    "Indian micro-entrepreneurs — street vendors, small shopkeepers, home-based "
    "producers, and first-time founders.\n\n"
    "You help with two things, always in short, plain, practical language:\n"
    "1. BUILDING the business: turn an idea into a real small business and grow "
    "it — business model, pricing, costs and cash flow, getting customers, "
    "registering the business (Udyam, GST), and managing money.\n"
    "2. LOAN-READINESS: help the user qualify for a loan — match ONLY the curated "
    "schemes below, explain eligibility, list required documents, and coach them "
    "on what to say at the bank.\n\n"
    "Style rules:\n"
    "- Warm, action-oriented, easy to understand; use bullets where helpful.\n"
    "- ALWAYS end with one concrete next step the user can do today.\n"
    "- Never invent schemes, amounts or numbers — only the curated list below.\n"
    "- If a question is not about business or loans, politely steer the user "
    "back to their business.\n"
    "- If the user refers to their own report/advisory context, answer using it.\n\n"
    f"CURATED INDIAN MSME SCHEMES (only these, never invent others):\n{_SCHEMES_EXCERPT}"
)

# Fallback keyword groups (deterministic, offline).
_DOC_KEYWORDS = ("document", "paper", "checklist", "form", "proof", "file", "paperwork")
_START_KEYWORDS = ("start", "idea", "begin", "plan", "how do i", "new business", "launch")

_GENERIC_FALLBACK = (
    "I'm offline right now, but I can still help you build and get loan-ready. "
    "Try asking: 'Which scheme fits my business?', 'What documents do I need?' or "
    "'How do I start a small business?'. For deeper analysis, run the research "
    "above to get your full Loan Readiness Advisory."
)


async def chat_agent(
    message: str,
    topic: str = "",
    advisory_context: str = "",
    chat_history: Optional[List[Dict[str, str]]] = None,
    agent_hint: str = "chat",
) -> str:
    """
    Answer a single chat turn. `chat_history` is the recent remembered
    conversation; `advisory_context` is the latest written advisory for the
    session, used when the user asks about their own report.
    """
    history: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    if advisory_context:
        history.append({
            "role": "system",
            "content": "The user's latest Loan Readiness Advisory (reference only):\n" + advisory_context[:2500],
        })

    for m in (chat_history or [])[-10:]:
        role = m.get("role") or "user"
        content = m.get("content") or ""
        if role in ("user", "assistant"):
            history.append({"role": role, "content": content})

    history.append({
        "role": "user",
        "content": f"User question (their current business topic: {topic or 'not provided'}): {message}",
    })

    try:
        reply = await call_llm(history, temperature=0.6, agent_hint=agent_hint)
        reply = (reply or "").strip()
        if reply:
            return reply
        logger.warning("[Chat] LLM returned empty reply")
    except Exception as e:
        logger.error(f"[Chat] LLM failed, using heuristic fallback: {e}")

    return _heuristic_reply(message, topic)


def _heuristic_reply(message: str, topic: str) -> str:
    """Deterministic, offline answer — specialised, actionable, on-scope."""
    lower = message.lower()
    schemes = match_schemes(topic or message)

    if any(k in lower for k in _DOC_KEYWORDS):
        checklist = [
            "a valid ID proof (Aadhaar or Voter ID)",
            "business proof (Udyam registration if you have it — it's free)",
            "bank statements for the last 6 months",
            "a rough monthly income/sales figure (an honest estimate)",
            "address proof of your business location",
        ]
        lines = "\n".join(f"• {item}" for item in checklist)
        top = f"\n\n{schemes[0]['name']} asks for the same list — keep a clean photo of every paper on your phone." if schemes else ""
        return (
            "Here is the standard document pack we coach people to carry to the "
            "bank (offline answer):\n"
            f"{lines}\n\nTip: keep this pack ready BEFORE you visit the bank — it "
            f"makes you look prepared and speeds up approval.{top}\n\n"
            "Next step today: put these documents in one folder or a clear photo album."
        )

    if any(k in lower for k in _START_KEYWORDS):
        return (
            "Starting a small business? Here is our building path (offline answer):\n"
            "• Business in one line — what you sell, to whom, at what price.\n"
            "• Costs — what you spend weekly to run it (stock, rent, transport).\n"
            "• Income — what customers actually pay you each week.\n"
            "• Prove it for 3 months — steady sales records are your best loan collateral.\n"
            "• Register free with the government: Udyam (udyamregistration.gov.in).\n"
            "• Start small with a micro loan (MUDRA - Shishu, up to ₹50,000) once "
            "your sales are regular.\n\n"
            "Next step today: write one line on paper — what you sell, to whom, "
            "at what price."
        )

    if schemes:
        lines = "\n".join(
            f"• {s['name']}: {s['loan_ceiling']} — {s['eligibility']}"
            for s in schemes
        )
        return (
            "Here are schemes that fit your business, from the local database "
            "(offline answer):\n"
            f"{lines}\n\n"
            "Next step today: pick the one whose ceiling your need fits, and "
            "start collecting its document checklist. Run the research above for "
            "a full written advisory."
        )

    return _GENERIC_FALLBACK