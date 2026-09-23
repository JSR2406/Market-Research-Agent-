"""
chat.py — specialised business-advisory & business-building chat agent.

Scope (stays on-topic):
  1. Building businesses — turning an idea into a viable small business: model,
     pricing, costs, cash flow, customers, registration (Udyam/GST), money habits.
  2. Loan-readiness advisory — matching curated schemes, eligibility, documents
     and "what to say at the bank".

Multi-language: replies follow the user's language — Hindi/Hinglish when they
write in Devanagari (or `lang="hi"` is set), English otherwise. The offline
heuristic fallback speaks Hindi too, so even with every LLM provider down the
chat stays useful for Hindi speakers.
"""
from __future__ import annotations

import logging
import re
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

# Detect Devanagari script -> Hindi/Hinglish intent.
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")

_DOC_KEYWORDS = (
    "document", "paper", "checklist", "form", "proof", "file", "paperwork",
    "काग़ज़", "कागज", "दस्तावेज़", "दस्तावेज", "प्रूफ़", "डॉक्यूमेंट", "डाक्यूमेंट",
)
_START_KEYWORDS = (
    "start", "idea", "begin", "new business", "launch", "how do i",
    "कैसे शुरू", "बिज़नेस शुरू", "शुरू करूँ", "शुरू करूं", "कैसे बनाऊँ", "कैसे बनाऊं", "आइडिया",
)

# ─────────────────────────────────────────────────────────────────────────────
# Offline (heuristic) replies — English and Hindi.
# ─────────────────────────────────────────────────────────────────────────────

_EN_DOC = (
    "Here is the standard document pack we coach people to carry to the "
    "bank (offline answer):\n"
    "• a valid ID proof (Aadhaar or Voter ID)\n"
    "• business proof (Udyam registration if you have it — it's free)\n"
    "• bank statements for the last 6 months\n"
    "• a rough monthly income/sales figure (an honest estimate)\n"
    "• address proof of your business location\n\n"
    "Tip: keep this pack ready BEFORE you visit the bank — it makes you look "
    "prepared and speeds up approval.\n\n"
    "Next step today: put these documents in one folder or a clear photo album."
)

_HI_DOC = (
    "बैंक जाने से पहले ये काग़ज़ तैयार रखें (offline जवाब):\n"
    "• पहचान पत्र — आधार या वोटर कार्ड\n"
    "• बिज़नेस का प्रमाण — उद्यम/रजिस्ट्रेशन (अगर है तो)\n"
    "• पिछले 6 महीने के बैंक स्टेटमेंट\n"
    "• अपनी आमदनी (मासिक बिक्री) का ईमानदार अनुमान\n"
    "• बिज़नेस की जगह का पता प्रमाण\n\n"
    "टिप: ये पैक बैंक जाने से पहले रख लें — लगता है कि आप तैयार हैं और मंज़ूरी जल्दी मिलती है।\n\n"
    "आज का कदम: इन सभी काग़ज़ों को एक फ़ोल्डर या फ़ोन के फ़ोटो एल्बम में रखें।"
)

_EN_START = (
    "Starting a small business? Here is our building path (offline answer):\n"
    "• Business in one line — what you sell, to whom, at what price.\n"
    "• Costs — what you spend weekly to run it (stock, rent, transport).\n"
    "• Income — what customers actually pay you each week.\n"
    "• Prove it for 3 months — steady sales records are your best loan collateral.\n"
    "• Register free with the government: Udyam (udyamregistration.gov.in).\n"
    "• Start small with a micro loan (MUDRA - Shishu, up to ₹50,000) once "
    "your sales are regular.\n\n"
    "Next step today: write one line on paper — what you sell, to whom, at what price."
)

_HI_START = (
    "छोटा बिज़नेस शुरू करना चाहते हैं? यह है बनाने का रास्ता (offline जवाब):\n"
    "• बिज़नेस एक लाइन में — क्या बेचेंगे, किसे, किस दाम पर\n"
    "• ख़र्चा — हफ़्ते में कितना लगता है (माल, किराया, आना-जाना)\n"
    "• आमदनी — ग्राहक हफ़्ते में कितना देते हैं\n"
    "• 3 महीने तक रिकॉर्ड रखें — नियमित बिक्री ही सबसे मज़बूत कर्ज़ का सबूत है\n"
    "• सरकारी रजिस्ट्रेशन फ़्री है: उद्यम (udyamregistration.gov.in)\n"
    "• बिक्री नियमित होने पर छोटे कर्ज़ से शुरुआत करें (मुद्रा - शिशु, ₹50,000 तक)\n\n"
    "आज का कदम: काग़ज़ पर एक लाइन लिखें — क्या बेचेंगे, किसे, किस दाम पर।"
)

_EN_GENERIC = (
    "I'm offline right now, but I can still help you build and get loan-ready. "
    "Try asking: 'Which scheme fits my business?', 'What documents do I need?' or "
    "'How do I start a small business?'. For deeper analysis, run the research "
    "above to get your full Loan Readiness Advisory."
)

_HI_GENERIC = (
    "मैं अभी ऑफ़लाइन हूँ, पर फिर भी बिज़नेस बनाने और कर्ज़ के लिए तैयार होने में मदद कर " 
    "सकता हूँ। पूछिए: 'मेरे बिज़नेस के लिए कौन-सी स्कीम है?', 'कौन-से काग़ज़ चाहिए?' या "
    "'छोटा बिज़नेस कैसे शुरू करूँ?'। पूरी जानकारी के लिए ऊपर research चलाइए — पूरी "
    "Loan Readiness Advisory मिलेगी।"
)


def _effective_lang(message: str, lang: str) -> str:
    """'hi' | 'en' — explicit lang wins, otherwise detect from the message."""
    if lang in ("hi", "en"):
        return lang
    return "hi" if _DEVANAGARI_RE.search(message) else "en"


async def chat_agent(
    message: str,
    topic: str = "",
    advisory_context: str = "",
    chat_history: Optional[List[Dict[str, str]]] = None,
    agent_hint: str = "chat",
    lang: str = "auto",
) -> str:
    """
    Answer a single chat turn. `chat_history` is the recent remembered
    conversation; `advisory_context` is the latest written advisory for the
    session, used when the user asks about their own report. `lang` is one of
    "auto" | "hi" | "en".
    """
    effective = _effective_lang(message, lang)

    history: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    if effective == "hi":
        history.append({
            "role": "system",
            "content": (
                "Reply ONLY in simple Hindi or Hinglish, written in Devanagari "
                "script. Keep scheme names, loan amounts and official terms "
                "(Udyam, GST, MUDRA, PM SVANidhi) in English. End with one "
                "concrete next step."
            ),
        })
    elif effective == "en":
        history.append({
            "role": "system",
            "content": "Reply in simple English only. End with one concrete next step.",
        })
    else:
        history.append({
            "role": "system",
            "content": (
                "Match the language the user writes in: if they write in Hindi "
                "or Hinglish, reply in Hindi/Hinglish; if English, reply in "
                "English. Keep scheme names and amounts in English. End with "
                "one concrete next step."
            ),
        })

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

    return _heuristic_reply(message, topic, effective)


def _heuristic_reply(message: str, topic: str, lang: str) -> str:
    """Deterministic, offline answer — specialised, actionable, on-scope."""
    lower = message.lower()
    hindi = lang == "hi"
    schemes = match_schemes(topic or message)

    if any(k in lower for k in _DOC_KEYWORDS):
        body = _HI_DOC if hindi else _EN_DOC
        if schemes:
            body += (
                f"\n\n{schemes[0]['name']} के लिए भी लगभग यही काग़ज़ चाहिए — सबके फ़ोटो फ़ोन में साफ़ रखें।"
                if hindi
                else f"\n\n{schemes[0]['name']} asks for the same list — keep a clean photo of every paper on your phone."
            )
        return body

    if any(k in lower for k in _START_KEYWORDS):
        return _HI_START if hindi else _EN_START

    if schemes:
        lines = "\n".join(
            f"• {s['name']}: {s['loan_ceiling']} — {s['eligibility']}"
            for s in schemes
        )
        if hindi:
            return (
                "आपके बिज़नेस के लिए ये स्कीमें मिलीं (local database से — offline जवाब):\n"
                f"{lines}\n\nआज का कदम: अपनी ज़रूरत के हिसाब से एक स्कीम चुनें और उसके काग़ज़ "
                "इकट्ठा करना शुरू करें। पूरी advisory के लिए ऊपर research चलाइए।"
            )
        return (
            "Here are schemes that fit your business, from the local database "
            "(offline answer):\n"
            f"{lines}\n\n"
            "Next step today: pick the one whose ceiling your need fits, and "
            "start collecting its document checklist. Run the research above for "
            "a full written advisory."
        )

    return _HI_GENERIC if hindi else _EN_GENERIC