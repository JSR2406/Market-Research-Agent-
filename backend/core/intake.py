"""
intake.py — the single canonical Business Check-up intake layer.

The Business Check-up is asked once, in the frontend stepper, but its answers
feed **every** surface: the research run (topic + synthesis), the advisor chat,
and the spoken advisory that is rendered from that run. This module is the one
place that knows what the intake fields are, so those surfaces cannot drift
apart.

Two rules from the product's data-accuracy principles are enforced here:

1. **The intake is structured, not prose.** Every answer is keyed by a stable
   field id (``business``, ``earnings``, ...) so we can tell *exactly* which
   detail is still missing. Asking "what should Saathi ask next?" is therefore a
   deterministic code decision — never an LLM guess.
2. **The client never dictates meaning.** Answers arrive as plain human-readable
   text (a chip label the user picked, or words they typed). Only this module
   turns them into the canonical snippet that the run and the prompts consume.

The field ids mirror ``frontend/lib/intake.ts``; ``tests/test_intake.py`` fails
if the two ever drift.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Intake answers are user-typed, so they are capped hard: a few hundred
# characters per field and a dozen fields is far more than any real answer.
MAX_FIELDS = 12
MAX_VALUE_CHARS = 200
MAX_SNIPPET_CHARS = 1500

# id, short label (for the canonical snippet), question (en), question (hi)
INTAKE_FIELDS: Tuple[Tuple[str, str, str, str], ...] = (
    (
        "business",
        "your business",
        "What kind of business is this?",
        "यह किस तरह का बिज़नेस है?",
    ),
    (
        "offering",
        "what you sell",
        "What exactly do you sell or do?",
        "आप क्या बेचते हैं या क्या काम करते हैं?",
    ),
    (
        "scale",
        "size of the business",
        "How big is the business?",
        "बिज़नेस कितना बड़ा है?",
    ),
    (
        "age",
        "time running",
        "How long has it been running?",
        "यह बिज़नेस कितने समय से चल रहा है?",
    ),
    (
        "earnings",
        "monthly earning",
        "Roughly how much do you earn in a month?",
        "महीने में लगभग कितना कमाते हैं?",
    ),
    (
        "location",
        "location",
        "Where is your business?",
        "आपका बिज़नेस कहाँ है?",
    ),
    (
        "loan",
        "past borrowing",
        "Have you taken a business loan before?",
        "क्या आपने पहले बिज़नेस लोन लिया है?",
    ),
    (
        "need",
        "main need",
        "What do you need most right now?",
        "अभी आपको सबसे ज़्यादा क्या चाहिए?",
    ),
    # Asked last, and only when it changes the advice (new business, or one
    # chasing money or paperwork) — mirrors the branching rule in intake.ts.
    (
        "registered",
        "registration",
        "Is the business registered (Udyam / GST)?",
        "क्या बिज़नेस रजिस्टर्ड है (उद्यम / GST)?",
    ),
)

FIELD_IDS: Tuple[str, ...] = tuple(f[0] for f in INTAKE_FIELDS)

_FIELD_BY_ID: Dict[str, Tuple[str, str, str]] = {
    fid: (label, q_en, q_hi) for fid, label, q_en, q_hi in INTAKE_FIELDS
}

# The order in which Saathi asks for what is still missing. Business identity
# and what the user sells come first — every downstream decision (scheme
# eligibility, cash-flow, research queries) depends on them.
GAP_PRIORITY: Tuple[str, ...] = (
    "business",
    "offering",
    "earnings",
    "location",
    "age",
    "loan",
    "need",
    "scale",
    "registered",
)

# Keywords that let the follow-up question adapt to the user's business type,
# e.g. a farmer is asked what they grow rather than what they sell.
#
# These are deliberately STRONG signals only. Single animal/product words are
# excluded on purpose: someone who "makes goat milk soap from my home" is a
# home-based producer, not a farmer, and asking them what they grow reads as
# nonsense. Bare "goat" / "cow" / "milk" only count next to a business noun.
_FARM_RE = re.compile(
    r"\b(farm|farming|farmland|dairy|cattle|poultry|goat\s*farm|cow\s*farm|"
    r"chicken\s*farm|agr[iie]?|agriculture|kheti|khet|zameen|kisan|"
    r"पशुपालन|पालन|डेयरी|खेती|किसान|खेत|ज़मीन)\w*",
    re.IGNORECASE,
)
_SERVICE_RE = re.compile(
    r"\b(service|repair|tuition|home[- ]?based|home\s*business|freelance|salon|"
    r"tailor|सेवा|सिलाई|ट्यूशन|फ्रीलांस|घर\s*पर)\w*",
    re.IGNORECASE,
)


def normalize_intake(raw: Optional[Dict]) -> Dict[str, str]:
    """
    Coerce a client-supplied intake into a clean ``{field_id: text}`` map.

    - unknown ids are dropped (a stale client cannot inject arbitrary keys),
    - values must be strings, are whitespace-collapsed and length-capped,
    - at most ``MAX_FIELDS`` fields survive, in canonical order,
    - empty answers are treated as unanswered.
    """
    if not isinstance(raw, dict):
        return {}

    cleaned: Dict[str, str] = {}
    for fid in FIELD_IDS:
        if len(cleaned) >= MAX_FIELDS:
            break
        value = raw.get(fid)
        if not isinstance(value, str):
            continue
        text = re.sub(r"\s+", " ", value).strip()
        if not text:
            continue
        cleaned[fid] = text[:MAX_VALUE_CHARS]
    return cleaned


def build_intake_snippet(intake: Optional[Dict]) -> str:
    """
    The canonical one-line profile used by the run topic, synthesis prompts and
    the advisor chat. Empty when nothing was answered.
    """
    answers = normalize_intake(intake)
    if not answers:
        return ""
    parts = [f"{_FIELD_BY_ID[fid][0]}: {answers[fid]}" for fid in FIELD_IDS if fid in answers]
    return ("Business profile — " + "; ".join(parts))[:MAX_SNIPPET_CHARS]


def missing_fields(intake: Optional[Dict]) -> List[str]:
    """Ids still unanswered, ordered by how much they improve the advisory."""
    answers = normalize_intake(intake)
    return [fid for fid in GAP_PRIORITY if fid not in answers]


def is_intake_complete(intake: Optional[Dict]) -> bool:
    return not missing_fields(intake)


def _business_is_farm(answers: Dict[str, str]) -> bool:
    return bool(_FARM_RE.search(answers.get("business", "")))


def _business_is_service(answers: Dict[str, str]) -> bool:
    return bool(_SERVICE_RE.search(answers.get("business", "")))


def next_question(intake: Optional[Dict], lang: str = "en") -> str:
    """
    The single most useful unanswered question, phrased for the business the
    user actually described (a farmer is asked what they grow; a service
    business what service they give). Returns "" when the intake is complete.
    """
    answers = normalize_intake(intake)
    gaps = missing_fields(answers)
    if not gaps:
        return ""

    gap = gaps[0]
    hindi = lang == "hi"
    if gap == "offering":
        if _business_is_farm(answers):
            return "आप क्या उगाते हैं या बेचते हैं?" if hindi else "What do you grow or sell?"
        if _business_is_service(answers):
            return "आप कौन-सी सेवा देते हैं?" if hindi else "What service or work do you do?"
        return "आप क्या बेचते हैं या क्या काम करते हैं?" if hindi else "What exactly do you sell or do?"
    if gap == "scale":
        if _business_is_farm(answers):
            return "आपके पास कितनी ज़मीन या कितने पशु हैं?" if hindi else "How much land or how many animals do you have?"
        return "आप रोज़ाना लगभग कितना बेचते हैं?" if hindi else "Roughly how much do you sell in a day?"
    return _FIELD_BY_ID[gap][2 if hindi else 1]


def followup_instruction(intake: Optional[Dict], lang: str = "en") -> str:
    """
    System-prompt guidance: if this question cannot be answered well without a
    detail the user has not given yet, ask for that ONE detail first (in the
    user's language) and then answer. Deterministic — we compute the gap in code.
    """
    gaps = missing_fields(intake)
    if not gaps:
        return ""
    question = next_question(intake, lang)
    if not question:
        return ""
    hindi = lang == "hi"
    still = ", ".join(_FIELD_BY_ID[fid][0] for fid in gaps[:4])
    if hindi:
        return (
            f"उपयोगकर्ता ने अभी तक ये नहीं बताया: {still}।\n"
            f"अगर सवाल का जवाब इन्हीं में से किसी बिना ठीक से नहीं दिया जा सकता, तो पहले "
            f"यह एक छोटा सवाल पूछें: \"{question}\" — और सीधा जवाब दें, लंबी बात नहीं।"
        )
    return (
        f"The user has NOT yet told you: {still}.\n"
        f"If their question cannot be answered well without one of these, ask for "
        f"that ONE detail first — \"{question}\" — and then answer immediately. "
        f"Keep it to one short question, never a list."
    )


def describe_missing(intake: Optional[Dict], lang: str = "en") -> str:
    """Short human line for the UI: "Still missing: business, earnings"."""
    gaps = missing_fields(intake)
    if not gaps:
        return ""
    labels = [_FIELD_BY_ID[fid][0] for fid in gaps[:4]]
    joined = ", ".join(labels)
    more = f" +{len(gaps) - 4} more" if len(gaps) > 4 else ""
    if lang == "hi":
        return f"अभी बाकी है: {joined}{more}"
    return f"Still to tell me: {joined}{more}"