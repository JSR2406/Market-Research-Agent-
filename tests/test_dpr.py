"""
tests/test_dpr.py — the Detailed Project Report builder and its PDF (WS-5).

A DPR is a document a bank reads, so this suite pins the two things that would
be embarrassing to get wrong: the arithmetic (projection growth, EMI, DSCR) and
the file itself (a real, multi-page PDF that carries the scheme's source link).
"""
import pytest

from backend.core.dpr import DISCLAIMER, build_dpr, dpr_to_pdf

INTAKE = {
    "business": "I make and sell candles in my home workshop",
    "offering": "decorative candles",
    "location": "Nagpur",
    "age": "3 years",
    "earnings": "40000 per month",
    "scale": "about 200 candles a week",
    "registered": "Yes, Udyam",
}

SECTION_IDS = [
    "executive_summary",
    "business_description",
    "market_analysis",
    "financial_projections",
    "assets",
    "management",
    "dscr",
    "annexure",
]


def _report(**kwargs):
    params = dict(
        intake=INTAKE,
        topic="",
        scheme_id="pmegp",
        project_cost=1000000,
        monthly_sales=120000,
        monthly_expenses=80000,
        lang="en",
    )
    params.update(kwargs)
    return build_dpr(**params)


def _section(report, section_id):
    return next(s for s in report["sections"] if s["id"] == section_id)


# ── structure ─────────────────────────────────────────────────────────────────


def test_report_has_every_expected_section_in_order():
    report = _report()
    assert [s["id"] for s in report["sections"]] == SECTION_IDS
    assert all(s["title"] for s in report["sections"])


def test_report_keeps_the_scheme_provenance():
    meta = _report()["meta"]
    assert meta["scheme_id"] == "pmegp"
    assert meta["source_url"].startswith("http")
    assert meta["last_verified_at"]
    assert meta["project_cost"] == 1000000


def test_missing_sales_yields_an_instruction_not_a_number():
    report = _report(monthly_sales=0, monthly_expenses=None)
    projections = _section(report, "financial_projections")
    assert projections["table"]["rows"] == []
    assert any("monthly sales" in line.lower() for line in projections["body"])
    assert _section(report, "dscr")["table"]["rows"] == []


# ── arithmetic ────────────────────────────────────────────────────────────────


def test_three_year_projection_follows_the_stated_growth():
    rows = _section(_report(), "financial_projections")["table"]["rows"]
    assert rows[0][1] == "₹14,40,000"  # 1,20,000 × 12
    assert rows[0][2] == "₹9,60,000"  # 80,000 × 12
    assert rows[0][3] == "₹4,80,000"
    assert rows[1][1] == "₹15,84,000"  # +10%
    assert rows[1][2] == "₹10,36,800"  # +8%
    assert len(rows) == 3


def test_dscr_uses_profit_plus_depreciation_over_debt_service():
    rows = _section(_report(), "dscr")["table"]["rows"]
    assert rows[0][2] == "₹1,00,000"  # 10% of a ₹10 lakh project, straight line
    assert rows[0][3] == "₹1,10,000"  # 11% of ₹10 lakh, year one
    # (4,80,000 profit + 1,00,000 depreciation) / (1,10,000 + principal) ≈ 2.2
    assert rows[0][5].startswith("2.2")
    # Debt service falls as the balance is repaid, so DSCR improves.
    assert float(rows[0][5]) < float(rows[1][5]) < float(rows[2][5])


def test_defaults_are_printed_as_assumptions():
    report = _report()
    text = " ".join(report["assumptions"])
    assert "10%" in text and "8%" in text
    assert "11.0%" in text
    assert "Depreciation" in text


def test_pmegp_subsidy_reaches_the_executive_summary():
    summary = " ".join(_section(_report(), "executive_summary")["body"])
    assert "₹1,50,000 – ₹3,50,000" in summary


def test_annexure_is_the_scheme_document_checklist():
    rows = _section(_report(), "annexure")["table"]["rows"]
    assert rows, "PMEGP's documents must reach the annexure"
    joined = " ".join(" ".join(r) for r in rows)
    assert "Aadhaar" in joined
    assert "Must have" in joined


def test_report_is_deterministic():
    assert _report() == _report()


# ── the PDF ───────────────────────────────────────────────────────────────────


def test_pdf_is_a_valid_multi_page_document():
    pdf = dpr_to_pdf(_report())
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page ") >= 2, "the report is long enough to paginate"
    assert b"/Count" in pdf


def test_pdf_footer_carries_the_source_and_the_disclaimer():
    report = _report()
    pdf = dpr_to_pdf(report)
    assert report["meta"]["source_url"].encode() in pdf
    assert report["meta"]["last_verified_at"].encode() in pdf
    assert b"Projections are estimates" in pdf


def test_pdf_never_ships_a_glyph_it_cannot_encode():
    pdf = dpr_to_pdf(_report())
    assert "\u20b9".encode("utf-8") not in pdf  # ₹ → "Rs."
    assert b"Rs." in pdf
    assert b"PMEGP" in pdf


def test_pdf_is_deterministic():
    assert dpr_to_pdf(_report()) == dpr_to_pdf(_report())


# ── language ──────────────────────────────────────────────────────────────────


def test_hindi_report_is_devanagari_and_not_mojibake():
    report = _report(lang="hi")
    text = " ".join(" ".join(s["body"]) for s in report["sections"])
    assert any("\u0900" <= ch <= "\u097f" for ch in text)
    assert "à¤" not in text
    assert report["disclaimer"] == DISCLAIMER["hi"]
    assert "PMEGP" in report["meta"]["scheme_name"]  # official term survives


def test_hindi_report_still_renders_an_english_pdf(client):
    """The PDF stays English (banks read English files) but must still be valid."""
    created = client.post(
        "/api/dpr", json={"intake": INTAKE, "scheme_id": "pmegp", "lang": "hi"}
    ).json()
    assert any("\u0900" <= ch <= "\u097f" for ch in created["report"]["sections"][0]["title"])
    pdf = client.get(created["pdf_url"])
    assert pdf.content.startswith(b"%PDF-")
    assert "\u20b9".encode("utf-8") not in pdf.content


# ── endpoint ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_endpoint_returns_a_job_and_a_downloadable_pdf(client):
    response = client.post(
        "/api/dpr",
        json={
            "intake": INTAKE,
            "scheme_id": "pmegp",
            "project_cost": 1000000,
            "monthly_sales": 120000,
            "monthly_expenses": 80000,
            "lang": "en",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "done"
    assert body["progress"]
    assert body["report"]["meta"]["scheme_id"] == "pmegp"

    pdf = client.get(body["pdf_url"])
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")


def test_endpoint_can_re_read_a_report(client):
    created = client.post("/api/dpr", json={"intake": INTAKE, "scheme_id": "pmegp"}).json()
    again = client.get(f"/api/dpr/{created['job_id']}")
    assert again.status_code == 200
    assert again.json()["report"]["sections"]


def test_unknown_job_is_a_clean_404(client):
    response = client.get("/api/dpr/does-not-exist")
    assert response.status_code == 404
    assert "expired" in response.json()["detail"].lower()


def test_endpoint_validates_the_cheap_fields(client):
    assert client.post("/api/dpr", json={"project_cost": 10}).status_code == 422
    assert client.post("/api/dpr", json={"project_cost": 10**12}).status_code == 422
    assert client.post("/api/dpr", json={"monthly_sales": -5}).status_code == 422


def test_a_hostile_session_id_is_ignored_not_used(client):
    response = client.post(
        "/api/dpr",
        json={"intake": INTAKE, "scheme_id": "pmegp", "session_id": "../../etc/passwd"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "done"
