"""
backend/core/heuristics.py — deterministic, zero-LLM advisory engine.

Used as a guaranteed fallback tier: when every LLM provider (Ollama / Hugging
Face / OpenRouter) is unavailable, these pure-Python functions still produce a
useful, topic-aware Loan Readiness Advisory and a low-literacy summary, so the
GrameenAI flow never dies with a blank response.

Also reused by the simplifier agent to build the plain-language document.
"""
import json
import os
import re
from typing import Dict, List, Optional

_SCHEMES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "schemes.json"
)

# Agents pass wrapped tasks ("Research Topic: ...\nContext: ...") — extracting
# the topic line prevents loan-ceiling figures in earlier outputs from being
# misread as the entrepreneur's income during heuristic fallback parsing.
_TOPIC_RE = re.compile(r"(?:Research Topic|Topic)\s*:\s*([^\n]+)", re.IGNORECASE)


def extract_topic(task: str) -> str:
    """Pull the actual topic/description out of an agent task string."""
    match = _TOPIC_RE.search(task)
    return match.group(1).strip() if match else task

# Scheme keyword guides (lowercase) used for deterministic matching.
_SCHEME_RULES: List[Dict] = [
    {
        "name_key": "street vendor",
        "scheme": "PM SVANidhi",
        "keywords": ["street vendor", "thela", "rehri", "vendor", "food cart", "stall"],
    },
    {
        "name_key": "first time",
        "scheme": "MUDRA - Shishu",
        "keywords": ["start", "new business", "first time", "begin", "launch"],
    },
    {
        "name_key": "expansion",
        "scheme": "MUDRA - Kishore",
        "keywords": ["expand", "growing", "scale", "machine", "equipment", "shop"],
    },
    {
        "name_key": "manufacturing",
        "scheme": "PMEGP",
        "keywords": ["manufactur", "production", "unit", "workshop", "factory", "artisan"],
    },
    {
        "name_key": "collateral free",
        "scheme": "CGTMSE",
        "keywords": ["sewing", "motor", "vehicle", "collateral", "loan without security", "udyam"],
    },
]


def load_schemes() -> List[Dict]:
    """Load the local Indian MSME scheme dataset as a list of dicts."""
    try:
        with open(_SCHEMES_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def schemes_json() -> str:
    """Serialized scheme data, used by agents for inline context."""
    return json.dumps(load_schemes(), indent=2, ensure_ascii=False)


def parse_amount(topic: str) -> Optional[int]:
    """
    Pull the most likely monthly earning figure (in INR) out of free text.
    Handles "₹15,000", "15000", "15k", "1.5 lakh", "₹25k/month".
    Returns None when nothing numeric is found.
    """
    compact = topic.lower().replace(",", "").strip()

    def _money(pat: str) -> Optional[int]:
        m = re.search(pat, compact)
        if not m:
            return None
        raw = m.group(1).replace(",", "")
        try:
            return int(raw)
        except ValueError:
            return None

    lakh = re.search(r"(\d+(?:\.\d+)?)\s*lakh", compact)
    if lakh:
        return int(float(lakh.group(1)) * 100_000)

    amount = _money(r"[₹rs]+\s*(\d+(?:\.\d+)?)\s*k")
    if amount is not None:
        return amount * 1000

    amount = _money(r"[₹rs]+\s*(\d+(?:\.\d+)?)")
    if amount is not None:
        return int(amount)

    amount = _money(r"(\d+(?:\.\d+)?)\s*k(?:/month|\s*per month)?")
    if amount is not None:
        return amount * 1000

    return None


def _display(amount: int) -> str:
    if amount >= 1_000_000:
        return f"₹{round(amount/100_000, 1)} lakh"
    return f"₹{amount:,}"


def match_schemes(topic: str, limit: int = 3) -> List[Dict]:
    """
    Score every scheme by keyword hits in the topic and return the best matches
    with their loan ceiling and a one-line eligibility note.
    """
    schemes = load_schemes()
    lower = topic.lower()
    scored: List[Dict] = []

    for scheme in schemes:
        name = scheme.get("scheme_name", "")
        text = lower + " " + name.lower() + " " + scheme.get("target_segment", "").lower()
        score = 0
        for rule in _SCHEME_RULES:
            if rule["scheme"].lower() in name.lower():
                if any(kw in lower for kw in rule["keywords"]):
                    score += 2
                else:
                    score += 1
        if any(kw in text for kw in ["collateral", "security"]):
            score += 1
        amount = parse_amount(topic)
        if amount:
            if amount < 50_000 and "shishu" in name.lower():
                score += 2
            if 50_000 <= amount <= 5_000_000 and "kishore" in name.lower():
                score += 2
            if amount > 5_000_000 and ("cgtsme" in name.lower() or "pmegp" in name.lower()):
                score += 2
        if "manufactur" in lower and "pmegp" in name.lower():
            score += 2
        if "street" in lower and "svanidhi" in name.lower():
            score += 2
        if score > 0:
            scored.append({"score": score, "scheme": scheme})

    scored.sort(key=lambda s: s["score"], reverse=True)
    return [
        {
            "name": s["scheme"].get("scheme_name", ""),
            "loan_ceiling": s["scheme"].get("loan_ceiling", ""),
            "eligibility": s["scheme"].get("one_line_eligibility", ""),
        }
        for s in scored[:limit]
    ]


def fallback_plan(topic: str) -> List[str]:
    """Topic-aware 5-step plan used when the planner LLM call fails."""
    short = topic[:60]
    return [
        f"Gather data on product/service and business model for {short}",
        f"Analyze daily/monthly income metrics and working capital need for {short}",
        f"Check location type, business registration, and eligibility profile for {short}",
        f"Match relevant Indian MSME schemes and document checklist for {short}",
        f"Synthesize findings into a final loan readiness advisory for {short}",
    ]


def build_heuristic_advisory(topic: str) -> Dict:
    """
    Deterministic Loan Readiness Advisory matching the writer/editor JSON schema:
    business_summary | cash_flow_snapshot | matched_schemes | documents_needed | next_step
    """
    amount = parse_amount(topic)
    matched = match_schemes(topic, limit=3)

    if amount:
        summary = (
            f"Based on your description, you appear to run a small informal business "
            f"with an estimated monthly earning of about {_display(amount)}. "
            "A short, carefully structured loan could help you invest in stock, "
            "tools, or equipment and grow your income."
        )
        cash_flow = {
            "estimated_monthly_revenue": _display(amount),
            "loan_range_suggestion": (
                f"₹{min(amount, 100000):,} – ₹{min(max(amount, 50000), 500000):,}"
            ),
            "repayment_assumption": "Assumed affordable at ~15-25% of monthly earnings",
        }
    else:
        summary = (
            "You described an informal small business. For a reliable loan estimate, "
            "please add your rough monthly earnings (e.g. 'I earn about ₹15,000 per month')."
        )
        cash_flow = {
            "estimated_monthly_revenue": "Not specified",
            "loan_range_suggestion": "Get Udyam registration first, then ask your bank",
            "repayment_assumption": "Pending income details",
        }

    documents_needed = [
        "Aadhaar card",
        "PAN card",
        "Active bank account statement (6 months)",
        "Two passport-size photographs",
    ]
    names = [m["name"] for m in matched]
    if any("CGTMSE" in n or "PMEGP" in n for n in names):
        documents_needed.append("Udyam registration certificate (free, online)")
    if any("SVANidhi" in n for n in names):
        documents_needed.append("Street vendor certificate / ULB identification")

    if matched:
        scheme_lines = [
            f"{m['name']} — loan ceiling {m['loan_ceiling']}."
            for m in matched
        ]
        matched_text_lines = scheme_lines
        next_step = (
            "1) Register your business on Udyam (free, online) if not already done. "
            "2) Visit the nearest bank / PM SVANidhi desk with identity papers. "
            "3) Apply with the matched scheme(s) listed above."
        )
    else:
        matched_text_lines = []
        next_step = (
            "1) Register your business on Udyam (free, online). "
            "2) Open/keep an active bank account. "
            "3) Ask your bank for a MUDRA loan — collateral-free and quick."
        )

    return {
        "business_summary": summary,
        "cash_flow_snapshot": cash_flow,
        "matched_schemes": matched_text_lines,
        "documents_needed": documents_needed,
        "next_step": next_step,
    }


def build_simplified_summary(advisory: Dict, topic: str = "") -> str:
    """
    Low-literacy, print-friendly plain-language summary of an advisory.
    Short numbered lines, no jargon — readable aloud to a first-time borrower.
    """
    summary = advisory.get("business_summary", "").strip()
    cash = advisory.get("cash_flow_snapshot", {})
    schemes = advisory.get("matched_schemes", []) or []
    next_step = advisory.get("next_step", "").strip()

    lines: List[str] = []
    lines.append("YOUR LOAN READINESS ADVISORY — IN SIMPLE WORDS")
    lines.append("")
    if summary:
        lines.append(f"1. About your business: {summary[:220]}")
    revenue = cash.get("estimated_monthly_revenue", "")
    if revenue:
        lines.append(f"2. Your rough monthly earning: {revenue}.")
    else:
        lines.append("2. Your rough monthly earning: not given. Add it for a sharper estimate.")
    if schemes:
        lines.append("3. You can apply for:")
        for i, s in enumerate(schemes[:3], start=1):
            lines.append(f"   - {s}")
    else:
        lines.append("3. You can apply for: a MUDRA loan from any bank (no security needed).")
    if next_step:
        lines.append(f"4. What to do next: {next_step[:220]}")
    lines.append("")
    lines.append("Remember: these are first hints. Always confirm exact terms at your bank.")
    return "\n".join(lines)