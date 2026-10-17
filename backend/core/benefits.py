"""
benefits.py — deterministic benefit / subsidy calculator.

Turns a rule-engine match into rupees *before* the user invests any effort:

    money you do NOT repay — PMEGP margin-money subsidy (published formula)
    money you DO repay     — loan ceilings (MUDRA tiers, PM SVANidhi tranches …)

Why this exists: a verdict ("eligible for MUDRA") still leaves the user asking
"so how much?" — and a language model answering that question invents numbers.
Here nothing is generated:

* percentages, project-cost ceilings and tranche ladders live in each record's
  ``benefit_rules`` (traceable to the record's ``source_url`` + ``last_verified_at``);
* tier bands come from the record's own ``min_amount``/``max_amount``;
* a scheme with no structured ``benefit_rules`` still gets a row, but only with
  the verified text the dataset already carries (ceiling, interest, collateral).

Deterministic and offline: no network, no LLM. The output always carries a
disclaimer, because the final number belongs to the sanctioning bank/authority.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.core.business import (
    HOME_BASED,
    MANUFACTURING,
    classify_business,
)
from backend.core.eligibility import (
    BLOCKED,
    ELIGIBLE,
    LIKELY,
    evaluate_schemes,
)
from backend.core.heuristics import load_schemes

logger = logging.getLogger(__name__)

# Shown on every response — the plan's rule is "disclaimer on every screen".
DISCLAIMER = {
    "en": (
        "Estimated from the scheme's published rules. Final amounts, interest "
        "and eligibility are decided by the sanctioning bank or authority — "
        "confirm the current figures on the official source before you apply."
    ),
    "hi": (
        "यह स्कीम के प्रकाशित नियमों से बना अनुमान है। अंतिम राशि, ब्याज और "
        "पात्रता स्वीकृति देने वाला बैंक या प्राधिकरण तय करता है — आवेदन से "
        "पहले आधिकारिक स्रोत पर मौजूदा आंकड़े ज़रूर देख लें।"
    ),
}

# Statuses whose rows count toward the headline totals ("the doors that are open").
_COUNTED = (ELIGIBLE, LIKELY)
# Rows worth showing at all — a blocked scheme still shows what the user would get
# once the one missing document is in hand.
_SHOWN = (ELIGIBLE, LIKELY, BLOCKED)

# Trigger for "is this money repaid?" — the dataset writes "Not a loan — …" for
# every grant / income-support / pension record, so this stays deterministic.
_NOT_A_LOAN = "not a loan"


# ── formatting helpers ────────────────────────────────────────────────────────

def format_inr(value: Optional[int]) -> str:
    """Indian-grouped rupees: 250000 → '₹2,50,000'."""
    if value is None:
        return "—"
    number = int(round(value))
    sign = "-" if number < 0 else ""
    digits = str(abs(number))
    if len(digits) <= 3:
        grouped = digits
    else:
        head, tail = digits[:-3], digits[-3:]
        parts: List[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts + [tail])
    return f"₹{sign}{grouped}"


def _is_repayable(scheme: Dict[str, Any]) -> bool:
    """False for grants / pensions / income support — never counted as credit."""
    rate = str(scheme.get("interest_rate") or "").strip().lower()
    return not rate.startswith(_NOT_A_LOAN)


def _sector_label(sector: str, lang: str) -> str:
    if lang == "hi":
        return "मैन्युफैक्चरिंग" if sector == "manufacturing" else "सेवा"
    return "manufacturing" if sector == "manufacturing" else "service"


def _pmegp_sector(business_class: str, secondary: List[str]) -> str:
    """
    PMEGP's subsidy table splits manufacturing from business/service.

    A home-based unit that *makes* its goods is production, so it takes the
    manufacturing ceiling; everything else (services, trade, other) takes the
    service ceiling. Ambiguity costs the user nothing — the ceiling is printed.
    """
    if business_class == MANUFACTURING:
        return "manufacturing"
    if business_class == HOME_BASED and MANUFACTURING in (secondary or []):
        return "manufacturing"
    return "service"


# ── per-scheme rows ───────────────────────────────────────────────────────────

def _pmegp_row(
    scheme: Dict[str, Any],
    sector: str,
    project_cost: Optional[int],
    lang: str,
) -> Optional[Dict[str, Any]]:
    """Margin-money subsidy math from the record's ``benefit_rules``."""
    rules = scheme.get("benefit_rules") or {}
    if rules.get("kind") != "margin_money":
        return None

    caps = rules.get("project_cost_cap") or {}
    cap = int(caps.get(sector) or 0) or None
    subsidy = rules.get("subsidy_pct") or {}
    own = rules.get("own_contribution_pct") or {}

    def pct(group: str, area: str) -> Optional[int]:
        value = ((subsidy.get(group) or {}).get(area))
        return int(value) if value is not None else None

    g_urban, g_rural = pct("general", "urban"), pct("general", "rural")
    s_urban, s_rural = pct("special", "urban"), pct("special", "rural")
    own_general, own_special = own.get("general"), own.get("special")

    lines: List[str] = []
    subsidy_min = subsidy_max = None
    own_min = own_max = None
    base = None

    if project_cost and cap:
        base = min(int(project_cost), cap)
        if lang == "hi":
            lines.append(
                f"मानी गई परियोजना लागत: {format_inr(project_cost)} — इतनी राशि पर सब्सिडी गिनी जाती है: "
                f"{format_inr(cap)} तक ({_sector_label(sector, lang)} परियोजना के लिए)।"
            )
            if int(project_cost) > cap:
                lines.append(
                    f"आपकी लागत {_sector_label(sector, lang)} की सीमा {format_inr(cap)} से ज़्यादा है, "
                    "इसलिए सब्सिडी सिर्फ़ सीमा तक की राशि पर मिलेगी।"
                )
        else:
            lines.append(
                f"Project cost considered: {format_inr(project_cost)} — subsidy is paid on up to "
                f"{format_inr(cap)} for a {_sector_label(sector, lang)} project."
            )
            if int(project_cost) > cap:
                lines.append(
                    f"Your cost is above the {_sector_label(sector, lang)} ceiling of {format_inr(cap)}, "
                    "so the subsidy is calculated on the ceiling amount only."
                )

        def amount(percent: Optional[int]) -> Optional[int]:
            return int(round(base * percent / 100)) if percent is not None else None

        subsidy_min, subsidy_max = amount(g_urban), amount(s_rural)
        own_min, own_max = amount(own_special), amount(own_general)

        if lang == "hi":
            lines.append(
                f"सामान्य श्रेणी की सब्सिडी: शहर में {g_urban}% = {format_inr(amount(g_urban))} · "
                f"गाँव में {g_rural}% = {format_inr(amount(g_rural))}"
            )
            lines.append(
                "विशेष श्रेणी (SC/ST/OBC/अल्पसंख्यक/महिला/ट्रांसजेंडर/भूतपूर्व सैनिक/दिव्यांग/NER/"
                "आकांक्षी जिला/पहाड़ी व सीमावर्ती क्षेत्र) की सब्सिडी: "
                f"शहर में {s_urban}% = {format_inr(amount(s_urban))} · "
                f"गाँव में {s_rural}% = {format_inr(amount(s_rural))}"
            )
            lines.append(
                f"आपका अपना हिस्सा: सामान्य {own_general}% ({format_inr(amount(own_general))}) / "
                f"विशेष {own_special}% ({format_inr(amount(own_special))})"
            )
            lines.append("बाकी राशि बैंक कर्ज़ के रूप में देगा — वह चुकानी पड़ती है।")
        else:
            lines.append(
                f"General category subsidy: {g_urban}% urban = {format_inr(amount(g_urban))} · "
                f"{g_rural}% rural = {format_inr(amount(g_rural))}"
            )
            lines.append(
                "Special category (SC/ST/OBC/minority/women/transgender/ex-servicemen/differently-abled/"
                "NER/aspirational district/hill & border) subsidy: "
                f"{s_urban}% urban = {format_inr(amount(s_urban))} · "
                f"{s_rural}% rural = {format_inr(amount(s_rural))}"
            )
            lines.append(
                f"Your own contribution: {own_general}% general ({format_inr(amount(own_general))}) / "
                f"{own_special}% special ({format_inr(amount(own_special))})"
            )
            lines.append("The bank gives a loan for the balance — that part is repaid.")
    else:
        # No project cost yet: publish the rule and one worked example per ₹1,00,000.
        example = 100_000
        ex_general = int(example * (g_urban or 0) / 100)
        ex_special = int(example * (s_rural or 0) / 100)
        if lang == "hi":
            lines.append(
                f"सब्सिडी दर: सामान्य — शहर {g_urban}% / गाँव {g_rural}% · विशेष — शहर {s_urban}% / गाँव {s_rural}%"
            )
            lines.append(
                f"अपनी परियोजना लागत भरें तो रुपये में अनुमान दिखेंगे (जैसे {format_inr(example)} पर "
                f"{format_inr(ex_general)} से {format_inr(ex_special)})।"
            )
        else:
            lines.append(
                f"Subsidy rates: general — {g_urban}% urban / {g_rural}% rural · "
                f"special — {s_urban}% urban / {s_rural}% rural"
            )
            lines.append(
                f"Enter your project cost to see rupee amounts (on {format_inr(example)}: "
                f"{format_inr(ex_general)} to {format_inr(ex_special)})."
            )

    # The subsidy is money the user keeps, but PMEGP also brings a bank loan:
    # ``loan_max`` is the project size the bank finances (90% general / 95%
    # special of it), so this row counts toward the credit-access ceiling too.
    return {
        "kind": "margin_money",
        "repayable": True,
        "lines": lines,
        "subsidy_min": subsidy_min,
        "subsidy_max": subsidy_max,
        "own_contribution_min": own_min,
        "own_contribution_max": own_max,
        "loan_min": None,
        "loan_max": base if base else cap,
    }


def _tiered_loan_row(
    scheme: Dict[str, Any],
    amount: Optional[int],
    lang: str,
) -> Optional[Dict[str, Any]]:
    """One MUDRA-tier row: the loan band this amount falls in."""
    rules = scheme.get("benefit_rules") or {}
    if rules.get("kind") != "tiered_loan":
        return None

    lo, hi = scheme.get("min_amount"), scheme.get("max_amount")
    band = (
        f"{format_inr(lo)} – {format_inr(hi)}"
        if lo
        else (f"{format_inr(hi)} तक" if lang == "hi" else f"up to {format_inr(hi)}")
    )
    lines: List[str] = []
    if lang == "hi":
        lines.append(f"इस श्रेणी की कर्ज़ राशि: {band}")
        lines.append("यह सब्सिडी नहीं है — यह कर्ज़ है और ब्याज आपका बैंक तय करता है।")
        lines.append("गिरवी (कोलैटरल) की ज़रूरत नहीं।")
        if amount and lo and hi and lo <= amount <= hi:
            lines.append(f"आपने {format_inr(amount)} माँगा — यह श्रेणी उसी में आती है।")
    else:
        lines.append(f"Loan range for this tier: {band}")
        lines.append("No subsidy — this is a loan and the interest is set by your bank.")
        lines.append("No collateral needed.")
        if amount and lo and hi and lo <= amount <= hi:
            lines.append(f"You asked for {format_inr(amount)} — this tier covers it.")

    return {
        "kind": "tiered_loan",
        "repayable": True,
        "lines": lines,
        "subsidy_min": None,
        "subsidy_max": None,
        "own_contribution_min": None,
        "own_contribution_max": None,
        "loan_min": lo,
        "loan_max": hi,
    }


def _tranche_row(scheme: Dict[str, Any], lang: str) -> Optional[Dict[str, Any]]:
    """PM SVANidhi's staged working-capital ladder."""
    rules = scheme.get("benefit_rules") or {}
    if rules.get("kind") != "tranche_ladder":
        return None

    tranches = rules.get("tranches") or []
    cap = rules.get("cumulative_cap") or (
        max((t.get("amount") or 0) for t in tranches) if tranches else None
    )

    if lang == "hi":
        steps = " → ".join(
            f"{t.get('amount') and format_inr(t.get('amount'))} ({t.get('tenor_months')} महीने)"
            for t in tranches
        )
        lines = [
            f"कर्ज़ चरणों में मिलता है: {steps}",
            "पहला कर्ज़ चुकाने के बाद ही अगला चरण मिलता है।",
            "समय पर चुकाने पर ब्याज पर छूट मिलती है; कर्ज़ राशि पर सब्सिडी नहीं है।",
        ]
    else:
        steps = " → ".join(
            f"{t.get('amount') and format_inr(t.get('amount'))} ({t.get('tenor_months')} months)"
            for t in tranches
        )
        lines = [
            f"The loan comes in tranches: {steps}",
            "The next tranche is available only after repaying the earlier one.",
            "Interest subsidy for on-time repayment; no subsidy on the loan amount itself.",
        ]

    return {
        "kind": "tranche_ladder",
        "repayable": True,
        "lines": lines,
        "subsidy_min": None,
        "subsidy_max": None,
        "own_contribution_min": None,
        "own_contribution_max": None,
        "loan_min": tranches[0].get("amount") if tranches else None,
        "loan_max": cap,
    }


def _dataset_row(scheme: Dict[str, Any], lang: str) -> Dict[str, Any]:
    """Fallback: only the verified text already in the curated record."""
    lines: List[str] = []
    ceiling = scheme.get("loan_ceiling")
    benefit = scheme.get("benefit_type")
    interest = scheme.get("interest_rate")
    collateral = scheme.get("collateral_requirement")

    if ceiling:
        lines.append(f"राशि: {ceiling}" if lang == "hi" else f"Amount: {ceiling}")
    if benefit:
        lines.append(f"सहायता का प्रकार: {benefit}" if lang == "hi" else f"Support type: {benefit}")
    if interest:
        lines.append(f"ब्याज: {interest}" if lang == "hi" else f"Interest: {interest}")
    if collateral:
        lines.append(f"गिरवी: {collateral}" if lang == "hi" else f"Collateral: {collateral}")

    return {
        "kind": "dataset",
        "repayable": _is_repayable(scheme),
        "lines": lines,
        "subsidy_min": None,
        "subsidy_max": None,
        "own_contribution_min": None,
        "own_contribution_max": None,
        "loan_min": None,
        "loan_max": scheme.get("max_amount"),
    }


# ── family collapse (MUDRA Shishu / Kishore / Tarun / Tarun+) ─────────────────

def _collapse_tiers(
    rows: List[Dict[str, Any]],
    amount: Optional[int],
    lang: str,
    family_tiers: Optional[Dict[str, List[Dict[str, Any]]]] = None,
) -> List[Dict[str, Any]]:
    """
    One row per programme, not one per tier.

    A user does not have four MUDRA loans — they have one, of some size. Keeping
    four rows would also sum four ceilings into a nonsense "total credit". The
    full ladder is still printed, read from the dataset (not from the matched
    subset, which is usually a single tier), so the user sees every rung.
    """
    family_tiers = family_tiers or {}
    by_family: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for row in rows:
        family = row.get("tier_group") or row["scheme_id"]
        if family not in by_family:
            order.append(family)
        by_family.setdefault(family, []).append(row)

    collapsed: List[Dict[str, Any]] = []
    for family in order:
        members = by_family[family]
        dataset_tiers = sorted(
            family_tiers.get(family) or [],
            key=lambda s: (s.get("min_amount") is None, s.get("min_amount") or 0),
        )
        if len(members) == 1 and len(dataset_tiers) <= 1:
            collapsed.append(members[0])
            continue

        best = max(
            members,
            key=lambda r: (r.get("status") == ELIGIBLE, r.get("score", 0)),
        )
        merged = dict(best)
        merged["lines"] = list(best["lines"])
        merged["tier_group"] = family

        def band_of(scheme: Dict[str, Any]) -> str:
            lo, hi = scheme.get("min_amount"), scheme.get("max_amount")
            if lo:
                return f"{format_inr(lo)} – {format_inr(hi)}"
            return f"{format_inr(hi)} तक" if lang == "hi" else f"up to {format_inr(hi)}"

        ladder = []
        for tier in dataset_tiers:
            label = str(tier.get("scheme_name", "")).split(" - ")[-1]
            mark = ""
            if tier.get("id") == best.get("scheme_id"):
                mark = " (यह)" if lang == "hi" else " (this one)"
            ladder.append(f"{label} {band_of(tier)}{mark}")

        merged["tiers"] = [
            {
                "scheme_id": tier.get("id", ""),
                "name": tier.get("scheme_name", ""),
                "status": next(
                    (m["status"] for m in members if m["scheme_id"] == tier.get("id")), ""
                ),
                "min_amount": tier.get("min_amount"),
                "max_amount": tier.get("max_amount"),
            }
            for tier in dataset_tiers
        ]
        lo_values = [t.get("min_amount") for t in dataset_tiers if t.get("min_amount") is not None]
        hi_values = [t.get("max_amount") for t in dataset_tiers if t.get("max_amount") is not None]
        merged["loan_min"] = min(lo_values) if lo_values else None
        # With a known amount, credit access = the tier that actually fits (a
        # Tarun-Plus ceiling is not available until a Tarun loan is repaid).
        # Without one, the family's own ceiling is the honest upper bound.
        if amount and best.get("loan_max"):
            merged["loan_max"] = best["loan_max"]
        else:
            merged["loan_max"] = max(hi_values) if hi_values else None

        if amount and merged["loan_max"] and amount > merged["loan_max"]:
            if lang == "hi":
                merged["lines"].append(
                    f"आपने {format_inr(amount)} माँगा — इस स्कीम की सबसे ऊँची सीमा "
                    f"{format_inr(merged['loan_max'])} है।"
                )
            else:
                merged["lines"].append(
                    f"You asked for {format_inr(amount)} — the top tier of this scheme is "
                    f"{format_inr(merged['loan_max'])}."
                )

        if ladder:
            programme = str(dataset_tiers[0].get("scheme_name", "")).split(" - ")[0]
            merged["lines"].append(
                (f"{programme} श्रेणियाँ: " if lang == "hi" else f"{programme} tiers: ")
                + " · ".join(ladder)
            )
        collapsed.append(merged)

    return collapsed


# ── public entry point ────────────────────────────────────────────────────────

def compute_benefits(
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
    amount: Optional[int] = None,
    project_cost: Optional[int] = None,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Estimate what a business could actually receive.

    ``project_cost`` is the user's own figure for PMEGP (a subsidy is a
    percentage of it); when it is missing we fall back to the loan amount the
    eligibility engine extracted, and if that is missing too the PMEGP row shows
    the published rates plus a worked example instead of a fabricated total.
    """
    lang = "hi" if lang == "hi" else "en"
    result = evaluate_schemes(intake, topic, amount, lang)
    answers = intake or {}
    classification = classify_business(answers, topic, lang)
    secondary = [str(c) for c in (classification.get("secondary") or [])]
    sector = _pmegp_sector(str(result.get("business_class") or ""), secondary)

    cost = project_cost if project_cost else result.get("amount")
    catalogue = load_schemes()
    schemes = {s.get("id"): s for s in catalogue}
    # tier_group → every record in that programme, so the ladder printed to the
    # user is the full published one, not just the tiers that happened to match.
    family_tiers: Dict[str, List[Dict[str, Any]]] = {}
    for record in catalogue:
        group = record.get("tier_group")
        if group:
            family_tiers.setdefault(group, []).append(record)
    verdicts = result.get("verdicts") or []

    rows: List[Dict[str, Any]] = []
    for verdict in verdicts:
        status = verdict.get("status")
        if status not in _SHOWN:
            continue
        scheme = schemes.get(verdict.get("scheme_id"))
        if not scheme:
            continue

        row = (
            _pmegp_row(scheme, sector, cost, lang)
            or _tiered_loan_row(scheme, result.get("amount"), lang)
            or _tranche_row(scheme, lang)
            or _dataset_row(scheme, lang)
        )
        row.update(
            {
                "scheme_id": scheme.get("id", ""),
                "scheme_name": scheme.get("scheme_name", ""),
                "benefit_type": scheme.get("benefit_type", ""),
                "tier_group": scheme.get("tier_group") or scheme.get("id", ""),
                "status": status,
                "status_label": verdict.get("status_label", ""),
                "score": verdict.get("score", 0),
                "source_url": scheme.get("source_url", ""),
                "last_verified_at": scheme.get("last_verified_at", ""),
            }
        )
        if status == BLOCKED:
            blocking = [
                r.get("label", "")
                for r in (verdict.get("reasons") or [])
                if r.get("severity") == "blocking"
            ]
            reason = blocking[0] if blocking else (verdict.get("status_label") or "")
            row["lines"] = [
                (
                    f"अभी रुका हुआ: {reason}" if lang == "hi" else f"Blocked for now: {reason}"
                )
            ] + list(row["lines"])
        rows.append(row)

    rows = _collapse_tiers(rows, result.get("amount"), lang, family_tiers)
    rows.sort(
        key=lambda r: (
            0 if r["status"] == ELIGIBLE else 1 if r["status"] == LIKELY else 2,
            -int(r.get("score") or 0),
            r.get("scheme_name", ""),
        )
    )

    counted = [r for r in rows if r["status"] in _COUNTED]
    subsidy_mins = [r["subsidy_min"] for r in counted if r.get("subsidy_min") is not None]
    subsidy_maxs = [r["subsidy_max"] for r in counted if r.get("subsidy_max") is not None]
    loan_ceiling = sum(
        int(r["loan_max"]) for r in counted if r.get("loan_max") and r.get("repayable")
    )

    if lang == "hi":
        assumptions = [
            "यह अनुमान आपके दिए जवाबों और स्कीम के प्रकाशित नियमों पर आधारित है।",
            "PMEGP की सब्सिडी आपके इलाके (शहर/गाँव) और श्रेणी (सामान्य/विशेष) पर निर्भर करती है — दोनों दरें दिखाई गई हैं।",
            "कर्ज़ चुकाना पड़ता है; सब्सिडी वाली राशि चुकानी नहीं पड़ती।",
        ]
        if cost:
            assumptions.append("लागत के आधार पर गिनती की गई राशि: " + format_inr(int(cost)))
    else:
        assumptions = [
            "The estimate follows your own answers and the scheme's published rules.",
            "PMEGP's subsidy depends on your area (rural/urban) and category (general/special) — every rate is shown above.",
            "Loans must be repaid; subsidy money does not have to be repaid.",
        ]
        if cost:
            assumptions.append("Figures calculated on a project cost of " + format_inr(int(cost)))

    if not counted and lang == "en":
        assumptions.append("No open scheme matched yet — answer a few more questions to see amounts.")

    return {
        "business_class": result.get("business_class", ""),
        "business_label": result.get("business_label", ""),
        "amount": result.get("amount"),
        "project_cost": int(cost) if cost else None,
        "pmegp_sector": sector,
        "rows": rows,
        "headline": {
            "subsidy_min": min(subsidy_mins) if subsidy_mins else None,
            "subsidy_max": max(subsidy_maxs) if subsidy_maxs else None,
            "loan_access": loan_ceiling,
            "matched_count": len(counted),
        },
        "assumptions": assumptions,
        "disclaimer": DISCLAIMER[lang],
    }


__all__ = ["compute_benefits", "format_inr", "DISCLAIMER"]
