"""
eligibility.py — deterministic scheme eligibility verdicts.

This is the module that makes the product different from a chatbot. A language
model asked "can I get a MUDRA loan?" produces confident prose. This engine
produces a *verdict* with a reason and a source, and it is allowed to say no:

    NOT_ELIGIBLE — a rule in schemes.json explicitly excludes this business
    WRONG_TIER   — the business qualifies, but this amount sits in another tier
    BLOCKED      — eligible on business type, held up by one missing document
    LIKELY       — no rule blocks it, but we lack a fact we would want
    ELIGIBLE     — every check passed

Design rules, in priority order:

1. **Code decides, the model explains.** Every verdict here is computed from
   `schemes.json` predicates and the user's own answers. The LLM never adds,
   softens or removes a verdict — it only writes prose around it.
2. **Every verdict cites its basis.** Each reason carries the `basis` string
   transcribed from the scheme's own eligibility/exclusion text, plus
   `source_url` and `last_verified_at`. An unsourced verdict is a bug.
3. **Silence is not agreement.** An unknown business class can never produce
   ELIGIBLE; it produces LIKELY with a note that we could not classify it.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from backend.core.business import (
    OTHER,
    is_known,
    classify_business,
)
from backend.core.heuristics import load_schemes, parse_amount
from backend.core.intake import normalize_intake

logger = logging.getLogger(__name__)

ELIGIBLE = "eligible"
LIKELY = "likely"
BLOCKED = "blocked"
NOT_ELIGIBLE = "not_eligible"
WRONG_TIER = "wrong_tier"

# Worst-first: this is the precedence used to collapse many reasons into one verdict.
_SEVERITY_RANK = {
    NOT_ELIGIBLE: 4,
    WRONG_TIER: 3,
    BLOCKED: 2,
    LIKELY: 1,
    ELIGIBLE: 0,
}

_SEVERITY_LABEL = {
    NOT_ELIGIBLE: "Not eligible",
    WRONG_TIER: "Wrong loan tier",
    BLOCKED: "Blocked",
    LIKELY: "Likely eligible",
    ELIGIBLE: "Eligible",
}

_MAX_REASONS = 6


def _registered_yes(intake: Dict[str, str]) -> bool:
    """True only when the user positively says the business is registered."""
    value = (intake.get("registered") or "").strip().lower()
    return value in {"yes, registered", "yes", "registered", "i have the udyam certificate"}


def _loan_history_value(intake: Dict[str, str]) -> str:
    """Map the loan answer onto a comparable lowercase token."""
    value = (intake.get("loan") or "").strip().lower()
    if "mudra" in value:
        return "mudra"
    if "bank" in value:
        return "bank"
    if "family" in value:
        return "family"
    if value in {"no, first time", "none", "first time"}:
        return "none"
    return ""


_LOAN_CUE_RE = re.compile(
    r"\bloan\b|\bborrow\b|\bborrowing\b|\blend\b|\budhaar\b|\bapply\b|"
    r"in\s*need\s*of\s*money|need\s*(a\s*)?loan|want\s*(a\s*)?loan|"
    r"paisa\s*chahiye|loan\s*(of|for)|कर्ज़|कर्ज|लेना|पैसा\s*चाहिए",
    re.IGNORECASE,
)


def _amount_for(topic: str, explicit: Optional[int]) -> Optional[int]:
    """
    The loan amount the user is actually asking for, or None.

    Deliberately conservative: a bare number is only read as a loan amount when
    the message also mentions borrowing. Using monthly earnings here would be
    wrong — someone earning ₹40,000 a month is not asking for a ₹40,000 loan,
    and tier advice built on that would actively mislead.
    """
    if explicit:
        return explicit
    if topic and _LOAN_CUE_RE.search(topic):
        return parse_amount(topic)
    return None


def _tier_for(amount: Optional[int], schemes: List[Dict], tier_group: str) -> Optional[Dict]:
    """Which tier of a tiered group actually covers this amount."""
    if amount is None:
        return None
    for scheme in schemes:
        if scheme.get("tier_group") != tier_group:
            continue
        lo = scheme.get("min_amount")
        hi = scheme.get("max_amount")
        if (lo is None or amount >= lo) and (hi is None or amount <= hi):
            return scheme
    return None


def _evaluate_check(
    check: Dict,
    classification: Dict,
    intake: Dict[str, str],
    lang: str = "en",
) -> Optional[Dict]:
    """One predicate → one reason, or None when the rule simply doesn't fire."""
    ctype = check.get("type")
    primary = classification["primary"]
    severity = check.get("severity", "advisory")
    # User-facing consequence in the language the site is set to. The English
    # label is always kept so a verdict never loses its meaning.
    label = (check.get("label_hi") if lang == "hi" else None) or check.get("label", "")
    basis = check.get("basis", "")

    if ctype == "business_class_not_in":
        blocked_classes = check.get("values") or []
        if primary in blocked_classes:
            return {
                "kind": "rule",
                "severity": severity,
                "label": label,
                "basis": basis,
            }
        return None

    if ctype == "business_class_in":
        allowed = check.get("values") or []
        if primary in allowed:
            return {"kind": "rule", "severity": "qualifying", "label": label, "basis": basis}
        # Only a *known* class can fail this. `other` means we did not
        # understand the business, which is not the same as failing the rule.
        if severity == "disqualifying" and is_known(primary):
            return {"kind": "rule", "severity": severity, "label": label, "basis": basis}
        return None

    if ctype == "requires_document":
        if _registered_yes(intake):
            return {"kind": "rule", "severity": "qualifying", "label": label, "basis": basis}
        return {
            "kind": "rule",
            "severity": "blocking",
            "label": label,
            "basis": basis,
            "action": "Get this document — it is the only thing standing between you and this scheme.",
        }

    if ctype == "loan_history_not":
        if _loan_history_value(intake) in (check.get("values") or []):
            return {
                "kind": "rule",
                "severity": "blocking",
                "label": label,
                "basis": basis,
            }
        return None

    if ctype in {"advisory", "collateral_note", "registration_preferred"}:
        return {"kind": "note", "severity": "advisory", "label": label, "basis": basis}

    logger.debug("[eligibility] unknown check type %s", ctype)
    return None


def _verdict_for(scheme: Dict, reasons: List[Dict], amount: Optional[int],
                 schemes: List[Dict], classification: Dict) -> Dict:
    severities = {r["severity"] for r in reasons}

    status = ELIGIBLE
    if "disqualifying" in severities:
        status = NOT_ELIGIBLE
    elif "blocking" in severities:
        status = BLOCKED
    else:
        lo, hi = scheme.get("min_amount"), scheme.get("max_amount")
        tier_group = scheme.get("tier_group")
        if amount is not None and tier_group and _tier_for(amount, schemes, tier_group) not in (None, scheme):
            status = WRONG_TIER
        elif not is_known(classification["primary"]):
            status = LIKELY
        elif not reasons or all(r["severity"] == "advisory" for r in reasons):
            status = LIKELY
        else:
            status = ELIGIBLE

    return {
        "scheme_id": scheme.get("id", ""),
        "name": scheme.get("scheme_name", ""),
        "status": status,
        "status_label": _SEVERITY_LABEL[status],
        # Once the business type disqualifies a scheme, a missing document is
        # noise — the certificate would not help. Keep the disqualifier only.
        "reasons": [
            r
            for r in reasons
            if not (status == NOT_ELIGIBLE and r["severity"] == "blocking")
        ][:_MAX_REASONS],
        "loan_ceiling": scheme.get("loan_ceiling", ""),
        "min_amount": scheme.get("min_amount"),
        "max_amount": scheme.get("max_amount"),
        "collateral_requirement": scheme.get("collateral_requirement", ""),
        "documents": list(scheme.get("documents") or [])[:6],
        "apply_via": scheme.get("apply_via", ""),
        "tier_group": scheme.get("tier_group", scheme.get("id", "")),
        "source_url": scheme.get("source_url", ""),
        "last_verified_at": scheme.get("last_verified_at", ""),
    }


def evaluate_schemes(
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
    amount: Optional[int] = None,
    lang: str = "en",
) -> Dict:
    """
    Evaluate every curated scheme against one business.

    Returns ``{"business_class", "amount", "verdicts", "by_status"}`` where
    ``verdicts`` is sorted worst-first — the user needs to know what they
    *cannot* do as much as what they can.
    """
    answers = normalize_intake(intake)
    classification = classify_business(answers, topic, lang)
    schemes = load_schemes()
    wanted = _amount_for(topic, amount)

    verdicts: List[Dict] = []
    for scheme in schemes:
        if not scheme.get("checks"):
            # A scheme without predicates cannot be judged — never guess.
            continue
        reasons = []
        for check in scheme.get("checks") or []:
            fired = _evaluate_check(check, classification, answers, lang)
            if fired:
                reasons.append(fired)

        verdict = _verdict_for(scheme, reasons, wanted, schemes, classification)

        if verdict["status"] == WRONG_TIER:
            better = _tier_for(wanted, schemes, scheme.get("tier_group"))
            if better is not None:
                verdict["suggested_scheme_id"] = better.get("id", "")
                verdict["suggested_name"] = better.get("scheme_name", "")
        verdicts.append(verdict)

    verdicts.sort(key=lambda v: (-_SEVERITY_RANK.get(v["status"], 0), v["name"]))

    by_status: Dict[str, List[str]] = {}
    for v in verdicts:
        by_status.setdefault(v["status"], []).append(v["scheme_id"])

    return {
        "business_class": classification["primary"],
        "business_label": classification["label"],
        "signals": classification["signals"],
        "amount": wanted,
        "verdicts": verdicts,
        "families": group_by_family({"verdicts": verdicts}),
        "by_status": by_status,
        "actionable": [v for v in verdicts if v["status"] in (ELIGIBLE, LIKELY, BLOCKED, WRONG_TIER)],
    }


def best_verdicts(result: Dict, limit: int = 3) -> List[Dict]:
    """The schemes worth showing first: open doors, then near-misses."""
    rank = {ELIGIBLE: 0, LIKELY: 1, WRONG_TIER: 2, BLOCKED: 3, NOT_ELIGIBLE: 4}
    ordered = sorted(result.get("verdicts") or [], key=lambda v: rank.get(v["status"], 9))
    return ordered[:limit]


def group_by_family(result: Dict) -> List[Dict]:
    """
    Collapse tiered programmes into one card each.

    MUDRA Shishu / Kishore / Tarun / Tarun+ are one scheme to a user, not four.
    Without this the UI shows three identical rows all saying "wrong tier, try
    Kishore" — technically true and completely useless.
    """
    families: Dict[str, List[Dict]] = {}
    for verdict in result.get("verdicts") or []:
        families.setdefault(verdict.get("tier_group") or verdict["scheme_id"], []).append(verdict)

    cards: List[Dict] = []
    for family, members in families.items():
        tiers = sorted(
            members,
            key=lambda v: (v.get("min_amount") is not None, v.get("min_amount") or 0),
        )
        best = min(members, key=lambda v: _SEVERITY_RANK.get(v["status"], 0))
        recommended = None
        for v in tiers:
            if v["status"] in (ELIGIBLE, LIKELY):
                recommended = v
                break
        card = {
            "family": family,
            "name": _short_name(tiers[0]["name"]),
            "status": best["status"],
            "status_label": best["status_label"],
            "reasons": best["reasons"],
            "documents": best["documents"],
            "collateral_requirement": best["collateral_requirement"],
            "apply_via": best["apply_via"],
            "source_url": best["source_url"],
            "last_verified_at": best["last_verified_at"],
            "recommended_scheme_id": (recommended or {}).get("scheme_id", ""),
            "recommended_name": (recommended or {}).get("name", ""),
            "tiers": [
                {
                    "scheme_id": t["scheme_id"],
                    "name": t["name"],
                    "status": t["status"],
                    "status_label": t["status_label"],
                    "min_amount": t.get("min_amount"),
                    "max_amount": t.get("max_amount"),
                    "loan_ceiling": t.get("loan_ceiling", ""),
                }
                for t in tiers
            ],
        }
        cards.append(card)

    cards.sort(key=lambda c: _SEVERITY_RANK.get(c["status"], 0))
    return cards


def eligibility_note_for(result: Dict, limit: int = 6) -> str:
    """
    The verdict block injected into the writer's prompt.

    Explicitly framed as overriding inference: the writer must not soften a
    disqualification or invent eligibility that the rule engine did not find.
    """
    families = result.get("families") or []
    if not families:
        return ""

    lines = [
        f"Business class (determined in code): {result.get('business_label', 'unknown')}",
    ]
    if result.get("signals"):
        lines.append(f"Evidence used: {'; '.join(result['signals'][:4])}")
    if result.get("amount"):
        lines.append(f"Loan amount stated by the client: {result['amount']}")

    for card in families[:limit]:
        verdict = card.get("status_label", "")
        line = f"- {card['name']}: {verdict}"
        if card.get("recommended_name") and card.get("status") != "not_eligible":
            line += f" (recommended tier: {card['recommended_name'].split('(')[0].strip()})"
        reasons = [r for r in (card.get("reasons") or []) if r.get("severity") in ("disqualifying", "blocking")]
        if reasons:
            line += f" — {reasons[0].get('label', '')}"
        lines.append(line)

    lines.append(
        "State these verdicts as they are. Never describe a 'not eligible' scheme "
        "as an option, and never promise a scheme the list above did not mark open."
    )
    return "\n".join(lines)


def _short_name(name: str) -> str:
    """'MUDRA (Micro Units ...) - Kishore' -> 'MUDRA'."""
    return name.split("(")[0].split("-")[0].strip() or name


def eligibility_summary(result: Dict) -> str:
    """One plain-language line for the advisor chat and the report header."""
    verdicts = result.get("verdicts") or []
    if not verdicts:
        return ""

    # Tiered schemes (MUDRA Shishu/Kishore/Tarun) are one programme to a user —
    # naming all four tiers would read as four different schemes.
    def unique_by_status(statuses: Tuple[str, ...], limit: int) -> List[str]:
        seen: List[str] = []
        for v in verdicts:
            if v["status"] not in statuses:
                continue
            label = _short_name(v["name"])
            if label not in seen:
                seen.append(label)
            if len(seen) >= limit:
                break
        return seen

    parts = [f"Business type: {result.get('business_label', 'unknown')}."]
    open_now = unique_by_status((ELIGIBLE, LIKELY), 3)
    blocked = unique_by_status((BLOCKED,), 2)
    closed = unique_by_status((NOT_ELIGIBLE,), 3)

    if open_now:
        parts.append(f"Open now: {', '.join(open_now)}.")
    if blocked:
        parts.append(f"Blocked on a document: {', '.join(blocked)}.")
    if closed:
        parts.append(f"Not for your business type: {', '.join(closed)}.")
    return " ".join(parts)