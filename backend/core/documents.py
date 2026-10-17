"""
documents.py — per-scheme document checklist (WS-4).

Turns the flat ``documents`` list in each curated scheme into something a user
can actually act on: grouped by who issues the paper (you / government / bank /
CA), split into must-have vs if-you-have-it, with a routing note that says where
the file is finally handed in.

Everything here is classification and wording — no figures, no model. A scheme
whose record carries no documents still gets the standard default set plus a
"confirm with your bank" note, because a blank checklist is worse than an
honest generic one.
"""
from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from backend.core.eligibility import BLOCKED, ELIGIBLE, LIKELY, evaluate_schemes
from backend.core.heuristics import load_schemes

logger = logging.getLogger(__name__)

ISSUER_ORDER = ("self", "govt", "bank", "ca")

ISSUER_LABELS: Dict[str, Dict[str, str]] = {
    "self": {"en": "You", "hi": "आप"},
    "govt": {"en": "Government office / registry", "hi": "सरकारी दफ़्तर / रजिस्ट्री"},
    "bank": {"en": "Bank", "hi": "बैंक"},
    "ca": {"en": "CA / professional", "hi": "CA / पेशेवर"},
}

REQUIRED_LABELS = {"en": "Must have", "hi": "ज़रूरी"}
OPTIONAL_LABELS = {"en": "If you have it", "hi": "अगर हो तो"}

# Used only when a scheme's own record lists nothing — deliberately the papers
# every Indian MSME credit file starts with, and always paired with the note.
DEFAULT_DOCUMENTS = [
    "Aadhaar card",
    "PAN card",
    "Business proof (shop agreement, licence or unit address)",
    "Bank statements (last 6 months)",
    "Passport-size photographs",
]

DISCLAIMER = {
    "en": (
        "Listed from the scheme's published requirements. Banks often ask for extra "
        "papers — confirm the final list at the branch before you submit."
    ),
    "hi": (
        "यह सूची स्कीम की प्रकाशित शर्तों से बनी है। बैंक अक्सर कुछ और कागज़ माँगते हैं — "
        "जमा करने से पहले शाखा में अंतिम सूची ज़रूर पूछ लें।"
    ),
}

DEFAULT_NOTE = {
    "en": "This scheme's own document list is not in our dataset yet — this is the usual set; confirm with your bank.",
    "hi": "इस स्कीम की कागज़ों की अपनी सूची हमारे डेटा में नहीं है — यह आम सूची है; बैंक से पुष्टि करें।",
}

BANK_ROUTING_NOTE = {
    "en": "Bank-led — carry this file to the branch; the bank decides the sanction.",
    "hi": "बैंक के ज़रिए — यह फ़ाइल शाखा में ले जाएँ; मंज़ूरी बैंक देता है।",
}

PORTAL_ROUTING_NOTE = {
    "en": "Apply first through the channel given below; papers are checked after that.",
    "hi": "पहले नीचे दिए रास्ते से आवेदन करें; कागज़ उसके बाद जाँचे जाते हैं।",
}

# Classifiers. Order matters: an "audited balance sheet" is a CA paper even
# though it is also a bank requirement, and Aadhaar/PAN are papers the user
# already holds — they belong under "You", not under a government office.
_CA_RE = re.compile(
    r"projected|balance sheet|profit|loss|dpr|project report|quotation|estimate|"
    r"audited|audit|chartered|financial statement|cma|dscr|cash flow|valuation|"
    r"cost of project|break[- ]?even",
    re.IGNORECASE,
)
_BANK_RE = re.compile(
    r"bank statement|loan account|sanction|cheque|bank account|account details|"
    r"repayment|emandate|credit report|cibil",
    re.IGNORECASE,
)
_GOVT_RE = re.compile(
    r"certificate|registration|licence|license|permit|udyam|gst|fssai|"
    r"vending|shop act|trade|noc|consent|income proof|caste|domicile|"
    r"affidavit|pan card of firm|partnership deed|incorporation",
    re.IGNORECASE,
)
_SELF_RE = re.compile(
    r"aadhaar|photo|identity|address proof|passport|voter|signature|"
    r"pan card|self[- ]declaration|undertaking",
    re.IGNORECASE,
)
_OPTIONAL_RE = re.compile(
    r"optional|if applicable|where applicable|if any|as applicable|if required",
    re.IGNORECASE,
)


def classify_document(text: str) -> Tuple[str, bool]:
    """
    Return ``(issuer, mandatory)`` for one document line.

    Defaults to ``("self", True)`` — the user can always file an unknown paper
    under their own set; marking something *optional* wrongly would be the
    harmful direction, so only an explicit phrase does that.
    """
    value = (text or "").strip()
    mandatory = not bool(_OPTIONAL_RE.search(value))
    if _CA_RE.search(value):
        issuer = "ca"
    elif _BANK_RE.search(value):
        issuer = "bank"
    elif _GOVT_RE.search(value):
        issuer = "govt"
    elif _SELF_RE.search(value):
        issuer = "self"
    else:
        issuer = "self"
    return issuer, mandatory


def _group_documents(documents: List[str], lang: str) -> List[Dict[str, Any]]:
    buckets: Dict[str, List[Dict[str, Any]]] = {issuer: [] for issuer in ISSUER_ORDER}
    seen = set()
    for raw in documents:
        text = str(raw or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        issuer, mandatory = classify_document(text)
        buckets[issuer].append(
            {"text": text, "mandatory": mandatory, "tag": (REQUIRED_LABELS if mandatory else OPTIONAL_LABELS)[lang]}
        )
    return [
        {"issuer": issuer, "label": ISSUER_LABELS[issuer][lang], "items": buckets[issuer]}
        for issuer in ISSUER_ORDER
        if buckets[issuer]
    ]


def _whatsapp_text(checklist: Dict[str, Any], lang: str) -> str:
    lines = [
        f"*{checklist['scheme_name']} — {'कागज़ों की सूची' if lang == 'hi' else 'document checklist'}*",
    ]
    if checklist.get("source_url"):
        lines.append(f"{checklist['source_url']} (verified {checklist['last_verified_at']})")
    for group in checklist["groups"]:
        lines.append("")
        lines.append(f"*{group['label']}*")
        for item in group["items"]:
            lines.append(f"- {item['text']}")
    if checklist.get("routing_note"):
        lines.append("")
        lines.append(f"{checklist['routing_note']} {checklist.get('apply_via') or ''}".strip())
    lines.append("")
    lines.append(DISCLAIMER[lang])
    return "\n".join(lines)


def build_checklist(scheme: Dict[str, Any], lang: str = "en") -> Dict[str, Any]:
    """One scheme → grouped checklist + routing note + share text."""
    lang = "hi" if lang == "hi" else "en"
    documents = [str(d) for d in (scheme.get("documents") or []) if str(d or "").strip()]
    used_defaults = not documents
    if used_defaults:
        documents = list(DEFAULT_DOCUMENTS)

    apply_via = str(scheme.get("apply_via") or "")
    bank_led = "bank" in apply_via.lower()

    checklist: Dict[str, Any] = {
        "scheme_id": scheme.get("id", ""),
        "scheme_name": scheme.get("scheme_name", ""),
        "tier_group": scheme.get("tier_group") or scheme.get("id", ""),
        "bank_led": bank_led,
        "routing_note": (BANK_ROUTING_NOTE if bank_led else PORTAL_ROUTING_NOTE)[lang],
        "apply_via": apply_via,
        "used_defaults": used_defaults,
        "groups": _group_documents(documents, lang),
        "source_url": scheme.get("source_url", ""),
        "last_verified_at": scheme.get("last_verified_at", ""),
    }
    checklist["whatsapp_text"] = _whatsapp_text(checklist, lang)
    return checklist


def build_document_plan(
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
    scheme_ids: Optional[List[str]] = None,
    lang: str = "en",
    limit: int = 6,
) -> Dict[str, Any]:
    """
    Checklists for the schemes that are open (or nearly open) for one business.

    ``scheme_ids`` lets a caller ask for specific schemes (the Scheme Explorer
    does); without it the rule engine decides, exactly as the verdict panel does,
    and tiered programmes collapse into a single checklist.
    """
    lang = "hi" if lang == "hi" else "en"
    catalogue = {s.get("id"): s for s in load_schemes()}

    if scheme_ids:
        wanted: List[str] = []
        for scheme_id in scheme_ids:
            scheme = catalogue.get(str(scheme_id))
            if scheme:
                family = scheme.get("tier_group") or scheme.get("id", "")
                if family not in wanted:
                    wanted.append(family)
        checklists = []
        for family in wanted[:limit]:
            members = [s for s in catalogue.values() if (s.get("tier_group") or s.get("id")) == family]
            checklists.append(build_checklist(members[0], lang))
        return {
            "generated_on": date.today().isoformat(),
            "checklists": checklists,
            "default_note": DEFAULT_NOTE[lang],
            "disclaimer": DISCLAIMER[lang],
        }

    result = evaluate_schemes(intake, topic, None, lang)
    seen_families: List[str] = []
    checklists = []
    for verdict in result.get("verdicts") or []:
        if verdict.get("status") not in (ELIGIBLE, LIKELY, BLOCKED):
            continue
        family = verdict.get("tier_group") or verdict.get("scheme_id", "")
        if family in seen_families:
            continue
        seen_families.append(family)
        scheme = catalogue.get(verdict.get("scheme_id"))
        if not scheme:
            continue
        checklist = build_checklist(scheme, lang)
        checklist["status"] = verdict.get("status", "")
        checklist["status_label"] = verdict.get("status_label", "")
        checklist["score"] = verdict.get("score", 0)
        checklists.append(checklist)

    # Verdicts arrive worst-first (you need to know what is closed too), but a
    # checklist is a to-do list: the open schemes belong at the top.
    rank = {ELIGIBLE: 0, LIKELY: 1, BLOCKED: 2}
    checklists.sort(key=lambda c: (rank.get(c.get("status", ""), 3), -int(c.get("score") or 0)))
    checklists = checklists[:limit]

    return {
        "generated_on": date.today().isoformat(),
        "checklists": checklists,
        "default_note": DEFAULT_NOTE[lang],
        "disclaimer": DISCLAIMER[lang],
    }


__all__ = [
    "build_checklist",
    "build_document_plan",
    "classify_document",
    "DEFAULT_DOCUMENTS",
    "DISCLAIMER",
]
