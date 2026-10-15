"""
ledger.py — the Action Ledger, and the loan-ready score derived from it.

The old `compute_loan_ready_score` scored the *report the LLM wrote*: it handed
out 20 points for the summary existing, 20 for having two numbers in the
cash-flow, 20 for the document checklist listing five items. Nobody had to do
anything. A user could reach 100/100 without ever registering a business.

This module replaces that with something a bank would actually recognise: a
list of actions the user can genuinely complete, each worth points, each with a
reason and a consequence. The score is a function of **the user's own state**,
not of prose quality.

The ledger is the seed of the executor half of the product. Each action carries
`unlocks`, so completing one changes what the eligibility engine can offer —
closing the loop between "what you can do" and "what to do next".

Everything here is deterministic. No LLM decides a score.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

from backend.core.eligibility import ELIGIBLE, LIKELY, evaluate_schemes
from backend.core.intake import normalize_intake

DONE = "done"
TODO = "todo"
BLOCKED = "blocked"

# 100 points total, weighted roughly the way a bank weighs them.
_ACTIONS: List[Dict] = [
    {
        "id": "register_udyam",
        "title": "Register the business on Udyam (free, online)",
        "points": 15,
        "why": "Udyam registration is how a bank sees you as a real enterprise. It costs nothing and takes about 10 minutes.",
        "how": "Register at udyamregistration.gov.in — you need Aadhaar and PAN.",
        "unlocks": ["cgtmse", "pmegp", "mudra-shishu"],
        # Pre-ticked from the intake when the user says they are registered,
        # but still tickable — plenty of people register without telling us.
        "user_confirmed": True,
    },
    {
        "id": "bank_statements",
        "title": "Keep 6 months of bank statements showing your business money",
        "points": 20,
        "why": "Steady, regular deposits are the single strongest thing you can show a lender. Six months of them turns 'trust me' into proof.",
        "how": "Depositing daily takings into your own account builds this automatically.",
        "unlocks": ["mudra-kishore", "mudra-tarun", "cgtmse"],
        "user_confirmed": True,
    },
    {
        "id": "income_declared",
        "title": "Know and write down your real monthly income",
        "points": 15,
        "why": "Banks price risk off your income. An honest rough figure — even a small one — beats a vague answer every time.",
        "how": "One honest monthly number is enough to start.",
        "unlocks": ["pmegp"],
        "user_confirmed": True,
    },
    {
        "id": "business_vintage",
        "title": "Run the business for at least 6 months",
        "points": 15,
        "why": "Lenders fund track records. Six months of trading history is what turns a first loan into a second one.",
        "how": "Keep trading consistently — regular sales matter more than big ones.",
        "unlocks": ["mudra-kishore", "mudra-tarun"],
        "user_confirmed": True,
    },
    {
        "id": "scheme_matched",
        "title": "Apply to a scheme that actually fits your business",
        "points": 15,
        "why": "Applying to the wrong scheme wastes a visit. Applying to the right one moves the loan forward.",
        "how": "See your eligibility verdict above — start with the ones marked open.",
        "unlocks": [],
    },
    {
        "id": "documents_ready",
        "title": "Keep your document pack ready in one folder",
        "points": 20,
        "why": "Every missing paper is a reason for the bank to say 'come back later'. One folder removes that excuse.",
        "how": "ID proof, Udyam certificate, 6 months statements, address proof, photos — all in one place, photographed on your phone.",
        "unlocks": [],
        "user_confirmed": True,
    },
]

# Street vendors only: this document is the gate on PM SVANidhi, so it is
# tracked as a blocker even though it carries no points.
_GATED_ACTIONS: List[Dict] = [
    {
        "id": "vending_certificate",
        "title": "Get your ULB / municipality vending certificate",
        "points": 0,
        "gates": ["pm-svanidhi"],
        "only_classes": ["street_vending"],
        "why": "PM SVANidhi is only for vendors holding a vending certificate. Without it the scheme is closed to you, no matter how well you trade.",
        "how": "Ask your municipal corporation or ULB for a vending certificate / identification letter.",
        "unlocks": ["pm-svanidhi"],
        "user_confirmed": True,
    }
]

_NEW_BIZ = re.compile(r"just started|under 3|^new$", re.IGNORECASE)
_HAS_NUMBER = re.compile(r"\d")


def _answers_say_registered(intake: Dict[str, str]) -> bool:
    value = (intake.get("registered") or "").strip().lower()
    return value in {"yes, registered", "yes", "registered", "i have the udyam certificate"}


def _auto_satisfied(action_id: str, intake: Dict[str, str], eligibility: Dict) -> Optional[bool]:
    """
    True/False when the intake already answers it, None when only the user can.

    Actions the intake settles are marked done immediately — asking someone to
    confirm what they just told us is friction.
    """
    if action_id == "register_udyam":
        return _answers_say_registered(intake) or None
    if action_id == "income_declared":
        value = (intake.get("earnings") or "").strip()
        if not value:
            return None
        return bool(_HAS_NUMBER.search(value)) or None
    if action_id == "business_vintage":
        value = (intake.get("age") or "").strip()
        if not value:
            return None
        return not bool(_NEW_BIZ.search(value))
    if action_id == "scheme_matched":
        statuses = {v["status"] for v in eligibility.get("verdicts") or []}
        return bool(statuses & {ELIGIBLE, LIKELY}) or None
    if action_id == "vending_certificate":
        return _answers_say_registered(intake) or None
    return None


def build_ledger(
    intake: Optional[Dict[str, str]] = None,
    eligibility: Optional[Dict] = None,
    topic: str = "",
    completed: Optional[Sequence[str]] = None,
) -> Dict:
    """
    Build the ledger for one business.

    ``completed`` is the user's own ticked list from previous visits — it is
    what makes the score climb over time instead of resetting each run.
    """
    answers = normalize_intake(intake)
    verdict = eligibility or evaluate_schemes(answers, topic)
    business_class = verdict.get("business_class", "other")
    ticked = {c for c in (completed or []) if isinstance(c, str)}

    catalog = list(_ACTIONS)
    for action in _GATED_ACTIONS:
        if business_class in (action.get("only_classes") or []):
            catalog.append(action)

    actions: List[Dict] = []
    for spec in catalog:
        auto = _auto_satisfied(spec["id"], answers, verdict)
        is_done = bool(auto) or spec["id"] in ticked

        blocked_by = ""
        if spec.get("gates") and business_class in (spec.get("only_classes") or []):
            blocked_by = "" if is_done else spec["why"]

        actions.append({
            "id": spec["id"],
            "title": spec["title"],
            "why": spec["why"],
            "how": spec["how"],
            "points": spec["points"],
            "unlocks": list(spec.get("unlocks") or []),
            "gates": list(spec.get("gates") or []),
            "status": DONE if is_done else TODO,
            "blocked_reason": blocked_by,
            "user_confirmable": bool(spec.get("user_confirmed")),
            "auto_answered": auto is True,
        })

    return {
        "actions": actions,
        "business_class": business_class,
        "amount": verdict.get("amount"),
    }


def _level(score: int) -> str:
    """Plain-language band — the number alone means nothing to a first-time borrower."""
    if score >= 85:
        return "Ready to apply"
    if score >= 60:
        return "Almost there"
    if score >= 35:
        return "Getting there"
    return "Early days"


def score_ledger(ledger: Dict) -> Dict:
    """
    The loan-ready score: points earned out of 100, every point explained.

    Deterministic, and derived only from actions the user has actually
    completed. Returns the next highest-value action so the score is always
    paired with a route forward.
    """
    actions = ledger.get("actions") or []
    total_possible = sum(int(a.get("points") or 0) for a in actions) or 100
    earned = sum(int(a.get("points") or 0) for a in actions if a.get("status") == DONE)

    score = int(round((earned / total_possible) * 100)) if total_possible else 0
    score = max(0, min(100, score))

    reasons: List[str] = []
    for action in actions:
        if action.get("status") == DONE:
            reasons.append(f"+{action['points']} — {action['title']}")
        elif action.get("points"):
            reasons.append(f"+{action['points']} waiting — {action['title']}")

    remaining = [a for a in actions if a.get("status") != DONE and (a.get("points") or 0)]
    remaining.sort(key=lambda a: int(a.get("points") or 0), reverse=True)
    next_action = remaining[0] if remaining else None

    # Gating documents are not points, but they can close a scheme entirely.
    blockers = [
        a for a in actions
        if a.get("gates") and a.get("status") != DONE
    ]

    return {
        "score": score,
        "level": _level(score),
        # `why` is kept in step with the older report-scoring shape so existing
        # renderers keep working; `reasons` is the field this module owns.
        "why": reasons[:8],
        "reasons": reasons[:8],
        "points_earned": earned,
        "points_possible": total_possible,
        "next_action": next_action,
        "blockers": blockers,
        "actions": actions,
        "done_count": sum(1 for a in actions if a.get("status") == DONE),
        "total_count": len(actions),
    }


def ledger_and_score(
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
    completed: Optional[Sequence[str]] = None,
    eligibility: Optional[Dict] = None,
) -> Dict:
    """Convenience: build + score in one call, returning both."""
    verdict = eligibility or evaluate_schemes(intake, topic)
    ledger = build_ledger(intake, verdict, topic, completed)
    scored = score_ledger(ledger)
    scored["business_class"] = verdict.get("business_class", "other")
    scored["amount"] = verdict.get("amount")
    return scored


def merge_completed(existing: Optional[Sequence[str]], incoming: Sequence[str]) -> List[str]:
    """Ticking an action is monotonic — users do not untick their own progress."""
    merged = {c for c in (existing or []) if isinstance(c, str)}
    merged.update(c for c in (incoming or []) if isinstance(c, str))
    return sorted(merged)