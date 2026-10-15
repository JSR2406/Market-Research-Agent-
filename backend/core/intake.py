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


def question_pack(lang: str = "en") -> Dict[str, str]:
    """
    Every field's question wording, in the site's language.

    The check-up stepper renders these so the questions a user reads are the
    same ones the gap detection reasons about — one source, no drift.
    """
    index = 2 if lang == "hi" else 1
    return {fid: entry[index] for fid, entry in _FIELD_BY_ID.items()}


def describe_missing(intake: Optional[Dict], lang: str = "en") -> str:
    gaps = missing_fields(intake)
    if not gaps:
        return ""
    labels = [_FIELD_BY_ID[fid][0] for fid in gaps[:4]]
    joined = ", ".join(labels)
    more = f" +{len(gaps) - 4} more" if len(gaps) > 4 else ""
    if lang == "hi":
        return f"अभी बाकी है: {joined}{more}"
    return f"Still to tell me: {joined}{more}"


# ─────────────────────────────────────────────────────────────────────────────
# Graded coverage — "answered" is not the same as "answered well".
#
# Asking "what do you earn?" and getting "some days" is not an answer a banker
# can use, and treating it as one is how a profile silently becomes useless.
# Each field is graded UNADDRESSED / THIN / ANSWERED, and THIN drives a gentle
# re-probe rather than being counted as done.
# ─────────────────────────────────────────────────────────────────────────────

UNADDRESSED = "unaddressed"
THIN = "thin"
ANSWERED = "answered"

# Fields the advisory leans on. `scale` and `registered` sharpen it but do not
# gate it, so they are excluded from the headline percentage.
CORE_FIELDS: Tuple[str, ...] = (
    "business",
    "offering",
    "earnings",
    "location",
    "age",
    "loan",
    "need",
)

_THIN_NOTES: Dict[str, Tuple[str, str]] = {
    "earnings": (
        "An honest rough figure works — lenders do not need an exact one.",
        "एक अनुमान भी चलेगा — सटीक नहीं चाहिए।",
    ),
    "location": (
        "Adding your city or district makes this far more useful.",
        "अपना शहर या ज़िला भी बताइए।",
    ),
    "offering": (
        "Naming what you sell helps us match the right scheme.",
        "यह बताइए कि आप क्या बेचते हैं — स्कीम सही से मिलेगी।",
    ),
    "scale": (
        "Even 'about 3000 a day' is enough to work with.",
        "रोज़ के 3000 रुपये भी काफ़ी हैं।",
    ),
}


def _tokens(value: str) -> List[str]:
    return [t for t in re.split(r"[\s,]+", value.strip()) if t]


def _grade(field_id: str, value: str) -> Tuple[str, str]:
    """Grade one answer: (status, why-it-is-thin)."""
    if not value:
        return UNADDRESSED, ""

    if field_id == "earnings":
        if not re.search(r"\d", value) and not re.search(
            r"under|above|below|less|more|around|approx|से|से कम|से ज्यादा|तक", value, re.IGNORECASE
        ):
            return THIN, _THIN_NOTES["earnings"][0]
        return ANSWERED, ""

    if field_id == "location":
        parts = _tokens(value)
        if len(parts) < 2 and not re.search(
            r"maharashtra|gujarat|rajasthan|p Pradesh|bengal|tamil|karnataka|telangana|madhya",
            value,
            re.IGNORECASE,
        ):
            return THIN, _THIN_NOTES["location"][0]
        return ANSWERED, ""

    if field_id in {"offering", "scale"}:
        if len(_tokens(value)) < 2 and len(value) < 8:
            return THIN, _THIN_NOTES[field_id][0]
        return ANSWERED, ""

    if field_id in {"business", "age", "loan", "need", "registered"}:
        # A picked chip is a complete answer; free text needs a little substance.
        if len(value) <= 3 and len(_tokens(value)) < 2:
            return THIN, "A few more words would help here."
        return ANSWERED, ""

    return ANSWERED, ""


def coverage_report(intake: Optional[Dict], lang: str = "en") -> Dict:
    """
    0-100 intake coverage with per-field grading.

    ``score`` counts a THIN answer as half — visible partial credit is what
    prompts the user to finish the answer instead of abandoning the form.
    """
    answers = normalize_intake(intake)
    fields: List[Dict] = []
    earned = 0.0

    for fid in GAP_PRIORITY:
        if fid not in CORE_FIELDS:
            continue
        label, q_en, q_hi = _FIELD_BY_ID[fid]
        value = answers.get(fid, "")
        status, note = _grade(fid, value)
        if status == ANSWERED:
            earned += 1.0
        elif status == THIN:
            earned += 0.5
        fields.append({
            "id": fid,
            "label": label,
            "status": status,
            "note": _THIN_NOTES[fid][1 if lang == "hi" else 0] if status == THIN else note,
            "question": q_hi if lang == "hi" else q_en,
        })

    score = int(round((earned / len(CORE_FIELDS)) * 100)) if CORE_FIELDS else 0

    optional = []
    for fid in GAP_PRIORITY:
        if fid in CORE_FIELDS:
            continue
        label, q_en, q_hi = _FIELD_BY_ID[fid]
        value = answers.get(fid, "")
        status, note = _grade(fid, value)
        optional.append({
            "id": fid,
            "label": label,
            "status": status,
            "note": note,
            "question": q_hi if lang == "hi" else q_en,
        })

    return {
        "score": max(0, min(100, score)),
        "fields": fields,
        "optional_fields": optional,
        "thin": [f["id"] for f in fields if f["status"] == THIN],
        "unaddressed": [f["id"] for f in fields if f["status"] == UNADDRESSED],
        "complete": not any(
            f["status"] != ANSWERED for f in fields
        ),
    }


def next_probe(intake: Optional[Dict], lang: str = "en") -> str:
    """
    The one question worth asking next.

    THIN answers outrank UNADDRESSED ones: a half-answer is closer to useful
    than an empty field, so we finish what the user already started before
    moving on to something they have not touched at all.
    """
    report = coverage_report(intake, lang)
    for wanted in (THIN, UNADDRESSED):
        for field in report["fields"]:
            if field["status"] == wanted:
                if wanted == THIN and field["note"]:
                    hint = f" ({field['note']})" if lang == "en" else f" ({field['note']})"
                    return f"{field['question']}{hint}"
                return field["question"]
    return ""