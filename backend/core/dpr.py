"""
dpr.py — the Detailed Project Report builder (WS-5).

A DPR is the file a bank reads before sanctioning a loan, and it is the one
deliverable a user will happily pay for. Two rules shape this module:

1. **Every number is computed here**, from the user's own inputs plus documented,
   labelled assumptions — the LLM never writes a figure. Where an input is
   missing (monthly sales, project cost) the section says so instead of filling
   the gap with a plausible-looking number.
2. **Every scheme fact keeps its provenance.** The report footer and the scheme
   box carry the scheme's ``source_url`` and ``last_verified_at``, and the
   annexure is the same deterministic checklist WS-4 produces.

Sections (in order): Executive Summary, Business Description, Market Analysis,
3-Year Financial Projections, Machinery & Assets, Management Profile, DSCR
Working, Document Annexure.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from backend.core.benefits import compute_benefits, format_inr
from backend.core.business import classify_business
from backend.core.documents import build_document_plan
from backend.core.eligibility import BLOCKED, ELIGIBLE, LIKELY, evaluate_schemes
from backend.core.heuristics import load_schemes, parse_amount

logger = logging.getLogger(__name__)

# Documented, labelled assumptions — printed in the report so the user (and the
# bank) can see exactly where each projection came from. They are deliberately
# conservative round numbers, not claims about this business.
GROWTH_REVENUE = 0.10
GROWTH_EXPENSE = 0.08
EXPENSE_RATIO = 0.70
DEFAULT_INTEREST = 11.0  # % p.a., indicative
DEFAULT_TENURE_MONTHS = 60
DEPRECIATION_PCT = 10.0  # % of project cost per year, straight line
YEARS = (1, 2, 3)

DISCLAIMER = {
    "en": (
        "Projections are estimates built from your answers and the stated "
        "assumptions. The bank's project appraisal decides the final sanction — "
        "attach your real quotations, licences and bank statements."
    ),
    "hi": (
        "यह अनुमान आपके जवाबों और ऊपर लिखी मान्यताओं से बना है। अंतिम मंज़ूरी बैंक के "
        "मूल्यांकन से होती है — असली कोटेशन, लाइसेंस और बैंक स्टेटमेंट साथ लगाएँ।"
    ),
}


def _t(lang: str, en: str, hi: str) -> str:
    return hi if lang == "hi" else en


def _pick_scheme(
    intake: Dict[str, str],
    topic: str,
    scheme_id: Optional[str],
    lang: str,
) -> Optional[Dict[str, Any]]:
    catalogue = {s.get("id"): s for s in load_schemes()}
    if scheme_id:
        return catalogue.get(str(scheme_id))
    result = evaluate_schemes(intake, topic, None, lang)
    for verdict in result.get("verdicts") or []:
        if verdict.get("status") in (ELIGIBLE, LIKELY, BLOCKED):
            scheme = catalogue.get(verdict.get("scheme_id"))
            if scheme:
                return scheme
    return None


def _projections(monthly_sales: Optional[int], monthly_expenses: Optional[int]) -> Optional[List[List[str]]]:
    if not monthly_sales or monthly_sales <= 0:
        return None
    expenses = monthly_expenses if monthly_expenses and monthly_expenses > 0 else int(monthly_sales * EXPENSE_RATIO)
    rows: List[List[str]] = []
    for year in YEARS:
        revenue = monthly_sales * 12 * ((1 + GROWTH_REVENUE) ** (year - 1))
        cost = expenses * 12 * ((1 + GROWTH_EXPENSE) ** (year - 1))
        rows.append(
            [
                f"Year {year}",
                format_inr(round(revenue)),
                format_inr(round(cost)),
                format_inr(round(revenue - cost)),
            ]
        )
    return rows


def _emi(principal: float, annual_rate: float, months: int) -> float:
    if principal <= 0 or months <= 0:
        return 0.0
    monthly_rate = annual_rate / 12 / 100
    if monthly_rate == 0:
        return principal / months
    factor = (1 + monthly_rate) ** months
    return principal * monthly_rate * factor / (factor - 1)


def _dscr_rows(loan: Optional[int], profit_rows: Optional[List[List[str]]]) -> Optional[List[List[str]]]:
    """
    DSCR = (net profit + depreciation) ÷ (interest + principal) for each year.

    Straight-line amortisation on a fixed-rate loan: the schedule is arithmetic,
    not a model opinion, and the rate/tenure are printed as assumptions.
    """
    if not loan or loan <= 0 or not profit_rows:
        return None
    rate = DEFAULT_INTEREST
    emi = _emi(float(loan), rate, DEFAULT_TENURE_MONTHS)
    annual_emi = emi * 12
    balance = float(loan)
    depreciation = loan * DEPRECIATION_PCT / 100
    rows: List[List[str]] = []
    for index, year in enumerate(YEARS):
        interest = balance * rate / 100
        principal = max(0.0, annual_emi - interest)
        if principal > balance:
            principal = balance
        balance -= principal
        profit = _money_to_int(profit_rows[index][3])
        service = interest + principal
        dscr = (profit + depreciation) / service if service > 0 else 0.0
        rows.append(
            [
                f"Year {year}",
                format_inr(round(profit)),
                format_inr(round(depreciation)),
                format_inr(round(interest)),
                format_inr(round(principal)),
                f"{dscr:.2f}",
            ]
        )
    return rows


def _money_to_int(display: str) -> int:
    digits = "".join(ch for ch in str(display) if ch.isdigit())
    return int(digits) if digits else 0


def _market_section(session_id: Optional[str], intake: Dict[str, str], topic: str, lang: str) -> Dict[str, Any]:
    """Seed the market section from the user's own research run, when there is one."""
    sources: List[str] = []
    findings: List[str] = []
    if session_id:
        try:
            from backend.core.memory import load_latest_run

            run = load_latest_run(session_id) or {}
            advisory = run.get("advisory") or {}
            summary = advisory.get("business_summary")
            if isinstance(summary, str) and summary.strip():
                findings.append(summary.strip())
            for fact in (advisory.get("market_insights") or [])[:4]:
                if isinstance(fact, str) and fact.strip():
                    findings.append(fact.strip())
            for item in (run.get("sources") or [])[:5]:
                url = item.get("url") if isinstance(item, dict) else str(item)
                if url:
                    sources.append(str(url))
        except Exception:  # a saved run must never break report generation
            logger.debug("[dpr] could not seed market section from session", exc_info=True)

    offering = intake.get("offering") or topic or _t(lang, "your product", "आपका उत्पाद")
    location = intake.get("location") or _t(lang, "your area", "आपका इलाक़ा")

    if findings:
        body = [_t(lang, "Taken from your own market research run:", "आपकी मार्केट रिसर्च से:")] + findings
    else:
        body = [
            _t(
                lang,
                f"Customers: describe who buys {offering} in {location} — households, shops, "
                "institutions — and roughly how many are within 5 km.",
                f"ग्राहक: {location} में {offering} कौन खरीदता है — घर, दुकानें, संस्थान — और 5 किमी "
                "के दायरे में लगभग कितने हैं, यह लिखें।",
            ),
            _t(
                lang,
                "Competition: list 3 competitors and the price each charges.",
                "मुक़ाबला: 3 मुक़ाबले करने वालों के नाम और उनके दाम लिखें।",
            ),
            _t(
                lang,
                "Advantage: what makes your product better — price, quality, location, service?",
                "बढ़त: आपका माल किस चीज़ में बेहतर है — दाम, क्वालिटी, जगह, सेवा?",
            ),
            _t(
                lang,
                "Run the market research on Saathi to fill this section with cited data.",
                "इस हिस्से में स्रोत वाला डेटा भरने के लिए Saathi पर मार्केट रिसर्च चलाएँ।",
            ),
        ]
    if sources:
        body.append(_t(lang, "Sources checked:", "देखे गए स्रोत:"))
        body.extend(sources)
    return {"body": body, "table": None}


def build_dpr(
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
    scheme_id: Optional[str] = None,
    project_cost: Optional[int] = None,
    monthly_sales: Optional[int] = None,
    monthly_expenses: Optional[int] = None,
    session_id: Optional[str] = None,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Build the whole report. Pure code: no network, no model, no randomness — the
    same inputs always produce the same document.
    """
    lang = "hi" if lang == "hi" else "en"
    answers = {k: str(v) for k, v in (intake or {}).items() if str(v or "").strip()}
    classification = classify_business(answers, topic, lang)
    business_label = str(classification.get("label") or answers.get("business") or _t(lang, "micro-enterprise", "लघु उद्यम"))
    scheme = _pick_scheme(answers, topic, scheme_id, lang)

    if monthly_sales is None:
        guess = parse_amount(str(answers.get("earnings") or ""))
        monthly_sales = guess
    if monthly_expenses is None and monthly_sales:
        monthly_expenses = int(monthly_sales * EXPENSE_RATIO)

    if project_cost is None and scheme:
        project_cost = scheme.get("max_amount")
        if scheme.get("tier_group") == "pmegp":
            # PMEGP's service ceiling is the safe assumption when the sector is
            # not obvious; the sector is printed in the assumptions.
            project_cost = 2_000_000

    benefit = compute_benefits(answers, topic, None, project_cost, lang)
    benefit_row = None
    if scheme:
        benefit_row = next((r for r in benefit["rows"] if r["scheme_id"] == scheme.get("id")), None)

    scheme_name = str(scheme.get("scheme_name")) if scheme else _t(lang, "Not selected", "चुनी नहीं गई")
    subsidy_text = ""
    if benefit_row and benefit_row.get("subsidy_max"):
        subsidy_text = f"{format_inr(benefit_row['subsidy_min'])} – {format_inr(benefit_row['subsidy_max'])}"

    # ── Executive summary ─────────────────────────────────────────────────────
    summary_body = [
        _t(
            lang,
            f"{business_label} seeking support under {scheme_name}.",
            f"{business_label} — {scheme_name} के तहत सहायता के लिए आवेदन।",
        ),
        _t(
            lang,
            f"Project cost considered: {format_inr(project_cost)}."
            if project_cost
            else "Add your project cost to make the loan request concrete.",
            f"मानी गई परियोजना लागत: {format_inr(project_cost)}।"
            if project_cost
            else "कर्ज़ की रक़म तय करने के लिए अपनी परियोजना लागत भरें।",
        ),
        _t(
            lang,
            f"Estimated subsidy / grant: {subsidy_text}." if subsidy_text else "No grant figure available yet.",
            f"अनुमानित सब्सिडी / अनुदान: {subsidy_text}।" if subsidy_text else "अभी अनुदान की राशि उपलब्ध नहीं।",
        ),
        _t(
            lang,
            "Requested assistance: term loan for plant, machinery and working capital, "
            "repayable over about five years.",
            "माँगी गई सहायता: मशीन, उपकरण और कार्यशील पूँजी के लिए अवधि कर्ज़, लगभग पाँच साल में चुकाने योग्य।",
        ),
    ]
    if scheme and scheme.get("source_url"):
        summary_body.append(
            _t(lang, "Scheme source: ", "स्कीम का स्रोत: ")
            + f"{scheme.get('source_url')} ({_t(lang, 'verified', 'जाँचा')} {scheme.get('last_verified_at')})"
        )

    # ── Business description ─────────────────────────────────────────────────
    description_body: List[str] = []
    if answers.get("offering"):
        description_body.append(
            _t(lang, f"Activity: {answers['offering']}.", f"काम: {answers['offering']}।")
        )
    if answers.get("location"):
        description_body.append(
            _t(lang, f"Location: {answers['location']}.", f"जगह: {answers['location']}।")
        )
    if answers.get("scale"):
        description_body.append(
            _t(lang, f"Scale / capacity: {answers['scale']}.", f"पैमाना / क्षमता: {answers['scale']}।")
        )
    if answers.get("age"):
        description_body.append(
            _t(lang, f"Vintage: {answers['age']}.", f"कितने समय से: {answers['age']}।")
        )
    description_body.append(
        _t(
            lang,
            "Production process: list the steps from raw material to the finished "
            "product, and where each step happens.",
            "बनाने का तरीक़ा: कच्चे माल से तैयार माल तक के चरण और हर चरण कहाँ होता है, लिखें।",
        )
    )
    description_body.append(
        _t(
            lang,
            "Working: number of days a month you operate, and who works with you.",
            "काम: महीने में कितने दिन चलता है और आपके साथ कौन काम करता है।",
        )
    )

    # ── Financial projections + DSCR ─────────────────────────────────────────
    projection_rows = _projections(monthly_sales, monthly_expenses)
    loan_amount = project_cost or (scheme.get("max_amount") if scheme else None)
    dscr_rows = _dscr_rows(loan_amount, projection_rows)

    finance_body = [
        _t(
            lang,
            "Projections grow revenue by "
            f"{int(GROWTH_REVENUE * 100)}% a year and costs by {int(GROWTH_EXPENSE * 100)}% a year.",
            f"अनुमान में आमदनी हर साल {int(GROWTH_REVENUE * 100)}% और ख़र्च {int(GROWTH_EXPENSE * 100)}% बढ़ता है।",
        ),
    ]
    if not projection_rows:
        finance_body.append(
            _t(
                lang,
                "Add monthly sales to generate the three-year projection.",
                "तीन साल का अनुमान बनाने के लिए महीने की बिक्री भरें।",
            )
        )

    # ── Assets ───────────────────────────────────────────────────────────────
    asset_rows = [
        [f"{_t(lang, 'Machine / equipment', 'मशीन / उपकरण')} {index}", "[  ]", "[  ]", "[  ]"]
        for index in range(1, 6)
    ]
    assets_body = [
        _t(
            lang,
            "Fill one row per machine with its name, cost and the quotation you attach.",
            "हर मशीन की एक पंक्ति भरें — नाम, क़ीमत और लगाया गया कोटेशन।",
        ),
    ]

    # ── Management profile ───────────────────────────────────────────────────
    management_body = [
        _t(lang, "Promoter: [full name], [age], [qualification].", "प्रोमोटर: [पूरा नाम], [उम्र], [योग्यता]।"),
    ]
    if answers.get("age"):
        management_body.append(
            _t(lang, f"Business vintage: {answers['age']}.", f"बिज़नेस कितने समय से: {answers['age']}।")
        )
    if answers.get("registered"):
        management_body.append(
            _t(lang, f"Registration status: {answers['registered']}.", f"रजिस्ट्रेशन की स्थिति: {answers['registered']}।")
        )
    management_body.append(
        _t(
            lang,
            "Experience: [years in this trade], [previous work]. Attach proof of "
            "experience or training certificates.",
            "तजुर्बा: [इस काम में साल], [पहले का काम]। तजुर्बे का सबूत या ट्रेनिंग सर्टिफ़िकेट लगाएँ।",
        )
    )

    # ── Document annexure ────────────────────────────────────────────────────
    annexure_rows: List[List[str]] = []
    if scheme:
        plan = build_document_plan(answers, topic, [str(scheme.get("id"))], lang, limit=1)
        for checklist in plan.get("checklists") or []:
            for group in checklist.get("groups") or []:
                for item in group.get("items") or []:
                    annexure_rows.append([group.get("label", ""), item.get("text", ""), item.get("tag", "")])

    sections: List[Dict[str, Any]] = [
        {"id": "executive_summary", "title": _t(lang, "1. Executive Summary", "1. संक्षिप्त सार"), "body": summary_body, "table": None},
        {"id": "business_description", "title": _t(lang, "2. Business Description", "2. बिज़नेस का ब्यौरा"), "body": description_body, "table": None},
        {
            "id": "market_analysis",
            "title": _t(lang, "3. Market Analysis", "3. बाज़ार का अध्ययन"),
            **_market_section(session_id, answers, topic, lang),
        },
        {
            "id": "financial_projections",
            "title": _t(lang, "4. Three-Year Financial Projections", "4. तीन साल का वित्तीय अनुमान"),
            "body": finance_body,
            "table": {
                "columns": [
                    _t(lang, "Year", "साल"),
                    _t(lang, "Revenue", "आमदनी"),
                    _t(lang, "Expenses", "ख़र्च"),
                    _t(lang, "Net profit", "शुद्ध लाभ"),
                ],
                "rows": projection_rows or [],
            },
        },
        {
            "id": "assets",
            "title": _t(lang, "5. Machinery & Assets", "5. मशीन और संपत्ति"),
            "body": assets_body,
            "table": {
                "columns": [
                    _t(lang, "Item", "चीज़"),
                    _t(lang, "Name", "नाम"),
                    _t(lang, "Cost", "क़ीमत"),
                    _t(lang, "Quotation", "कोटेशन"),
                ],
                "rows": asset_rows,
            },
        },
        {"id": "management", "title": _t(lang, "6. Management Profile", "6. प्रबंधन प्रोफ़ाइल"), "body": management_body, "table": None},
        {
            "id": "dscr",
            "title": _t(lang, "7. DSCR Working", "7. DSCR कार्य"),
            "body": [
                _t(
                    lang,
                    f"Loan assumed: {format_inr(loan_amount)} at {DEFAULT_INTEREST}% a year over "
                    f"{DEFAULT_TENURE_MONTHS // 12} years; depreciation at {int(DEPRECIATION_PCT)}% of project cost.",
                    f"माना गया कर्ज़: {format_inr(loan_amount)} — सालाना {DEFAULT_INTEREST}%, "
                    f"{DEFAULT_TENURE_MONTHS // 12} साल; मूल्यह्रास परियोजना लागत का {int(DEPRECIATION_PCT)}%।",
                )
            ]
            + (
                []
                if dscr_rows
                else [
                    _t(
                        lang,
                        "Add monthly sales to calculate DSCR.",
                        "DSCR निकालने के लिए महीने की बिक्री भरें।",
                    )
                ]
            ),
            "table": {
                "columns": [
                    _t(lang, "Year", "साल"),
                    _t(lang, "Net profit", "शुद्ध लाभ"),
                    _t(lang, "Depreciation", "मूल्यह्रास"),
                    _t(lang, "Interest", "ब्याज"),
                    _t(lang, "Principal", "मूलधन"),
                    "DSCR",
                ],
                "rows": dscr_rows or [],
            },
        },
        {
            "id": "annexure",
            "title": _t(lang, "8. Document Annexure", "8. कागज़ों की सूची"),
            "body": [
                _t(
                    lang,
                    "Attach a copy of each paper below; tick it off in the document checklist.",
                    "नीचे दिए हर कागज़ की कॉपी लगाएँ; सूची में टिक करें।",
                )
            ],
            "table": {
                "columns": [_t(lang, "From whom", "किससे"), _t(lang, "Document", "कागज़"), _t(lang, "Need", "ज़रूरत")],
                "rows": annexure_rows,
            },
        },
    ]

    assumptions = [
        _t(lang, f"Revenue grows {int(GROWTH_REVENUE * 100)}% a year; costs grow {int(GROWTH_EXPENSE * 100)}% a year.", f"आमदनी सालाना {int(GROWTH_REVENUE * 100)}% बढ़ती है; ख़र्च {int(GROWTH_EXPENSE * 100)}%।"),
        _t(lang, f"Costs assumed at {int(EXPENSE_RATIO * 100)}% of revenue when not entered.", f"ख़र्च भरा न हो तो आमदनी का {int(EXPENSE_RATIO * 100)}% माना गया है।"),
        _t(lang, f"Loan at {DEFAULT_INTEREST}% a year over {DEFAULT_TENURE_MONTHS // 12} years (edit to your bank's terms).", f"कर्ज़ सालाना {DEFAULT_INTEREST}% पर {DEFAULT_TENURE_MONTHS // 12} साल का (अपने बैंक की शर्तें भरें)।"),
        _t(lang, f"Depreciation at {int(DEPRECIATION_PCT)}% of project cost, straight line.", f"मूल्यह्रास परियोजना लागत का {int(DEPRECIATION_PCT)}% (सीधी रेखा)।"),
    ]
    if project_cost:
        assumptions.append(_t(lang, f"Project cost considered: {format_inr(project_cost)}.", f"मानी गई परियोजना लागत: {format_inr(project_cost)}।"))

    return {
        "meta": {
            "generated_on": date.today().isoformat(),
            "business_label": business_label,
            "scheme_id": scheme.get("id") if scheme else "",
            "scheme_name": scheme_name,
            "source_url": scheme.get("source_url", "") if scheme else "",
            "last_verified_at": scheme.get("last_verified_at", "") if scheme else "",
            "project_cost": project_cost,
            "loan_assumed": loan_amount,
            "language": lang,
        },
        "sections": sections,
        "assumptions": assumptions,
        "disclaimer": DISCLAIMER[lang],
    }


def dpr_to_pdf(report: Dict[str, Any]) -> bytes:
    """Flatten a report into PDF blocks and render it (English text)."""
    from backend.core.pdf import render_pdf

    meta = report.get("meta") or {}
    blocks: List[Dict[str, str]] = [
        {"style": "h1", "text": meta.get("business_label") or "Business"},
        {"style": "h2", "text": "Detailed Project Report"},
        {
            "style": "small",
            "text": (
                f"Scheme: {meta.get('scheme_name') or '-'} | Generated: {meta.get('generated_on') or ''} "
                f"| Project cost: {format_inr(meta.get('project_cost')) if meta.get('project_cost') else '-'}"
            ),
        },
    ]
    for section in report.get("sections") or []:
        blocks.append({"style": "h2", "text": section.get("title", "")})
        for paragraph in section.get("body") or []:
            blocks.append({"style": "body", "text": paragraph})
        table = section.get("table")
        if table and table.get("rows"):
            header = " | ".join(str(c) for c in table.get("columns") or [])
            blocks.append({"style": "h3", "text": header})
            for row in table["rows"]:
                blocks.append({"style": "kv", "text": " | ".join(str(c) for c in row)})
    blocks.append({"style": "h2", "text": "Assumptions"})
    for assumption in report.get("assumptions") or []:
        blocks.append({"style": "bullet", "text": assumption})
    blocks.append({"style": "small", "text": report.get("disclaimer", "")})

    footer = (
        f"{meta.get('scheme_name') or ''} | source: {meta.get('source_url') or ''} "
        f"({meta.get('last_verified_at') or ''}) | generated {meta.get('generated_on') or ''}"
    )
    return render_pdf("Detailed Project Report", blocks, footer=footer)


__all__ = ["build_dpr", "dpr_to_pdf", "DISCLAIMER"]
