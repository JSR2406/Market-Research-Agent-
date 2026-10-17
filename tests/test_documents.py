"""
tests/test_documents.py — the per-scheme document checklist (WS-4).

The checklist is a to-do list a user takes to a bank counter, so the two things
worth pinning are: documents land in the right group, and nothing is ever marked
"optional" unless the scheme's own text says so.
"""
import pytest

from backend.core.documents import (
    DEFAULT_DOCUMENTS,
    DISCLAIMER,
    build_checklist,
    build_document_plan,
    classify_document,
)
from backend.core.heuristics import load_schemes

MANUFACTURER = {
    "business": "I make and sell candles in my home workshop",
    "offering": "decorative candles",
}


def _scheme(scheme_id):
    return next(s for s in load_schemes() if s["id"] == scheme_id)


def _items(checklist):
    return [item for group in checklist["groups"] for item in group["items"]]


# ── classification ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,issuer",
    [
        ("Aadhaar card", "self"),
        ("PAN card", "self"),
        ("Passport-size photographs", "self"),
        ("Udyam registration certificate", "govt"),
        ("GST registration copy", "govt"),
        ("Bank statements (last 6 months)", "bank"),
        ("Projected balance sheet (3 years)", "ca"),
        ("Quotation for machinery", "ca"),
    ],
)
def test_documents_are_grouped_by_who_issues_them(text, issuer):
    assert classify_document(text)[0] == issuer


def test_only_explicit_wording_makes_a_document_optional():
    assert classify_document("Caste certificate (if applicable)")[1] is False
    assert classify_document("Caste certificate")[1] is True
    assert classify_document("GST registration (if any)")[1] is False


# ── one scheme ────────────────────────────────────────────────────────────────


def test_bank_led_scheme_says_carry_the_file_to_the_branch():
    checklist = build_checklist(_scheme("pmegp"))
    assert checklist["bank_led"] is True
    assert "branch" in checklist["routing_note"].lower()
    issuers = [g["issuer"] for g in checklist["groups"]]
    assert "self" in issuers
    assert checklist["source_url"].startswith("http")
    assert checklist["last_verified_at"]


def test_scheme_without_documents_gets_the_default_set_and_a_note():
    checklist = build_checklist({"id": "x", "scheme_name": "Test Scheme", "apply_via": "Any bank branch"})
    assert checklist["used_defaults"] is True
    assert {i["text"] for i in _items(checklist)} == set(DEFAULT_DOCUMENTS)


def test_no_duplicate_documents_in_a_checklist():
    checklist = build_checklist(_scheme("mudra-kishore"))
    texts = [i["text"].lower() for i in _items(checklist)]
    assert len(texts) == len(set(texts))


# ── plan across schemes ───────────────────────────────────────────────────────


def test_open_schemes_are_listed_before_blocked_ones():
    plan = build_document_plan(MANUFACTURER, "", None, "en", limit=6)
    assert plan["checklists"], "a manufacturer must get at least one checklist"
    statuses = [c["status"] for c in plan["checklists"]]
    assert statuses[0] in ("eligible", "likely")
    rank = {"eligible": 0, "likely": 1, "blocked": 2}
    assert [rank[s] for s in statuses] == sorted(rank[s] for s in statuses)


def test_named_schemes_are_used_and_tiered_programmes_collapse():
    plan = build_document_plan(None, "", ["mudra-kishore", "mudra-tarun"], "en")
    assert len(plan["checklists"]) == 1, "two MUDRA tiers are one checklist"
    assert "MUDRA" in plan["checklists"][0]["scheme_name"]


def test_unknown_scheme_ids_are_ignored_not_echoed():
    plan = build_document_plan(None, "", ["../../etc/passwd", "nope"], "en")
    assert plan["checklists"] == []


def test_plan_is_carries_a_date_and_a_disclaimer():
    plan = build_document_plan(MANUFACTURER, "", ["pmegp"], "en")
    assert len(plan["generated_on"]) == 10 and plan["generated_on"][4] == "-"
    assert plan["disclaimer"] == DISCLAIMER["en"]


# ── share + language ──────────────────────────────────────────────────────────


def test_whatsapp_text_is_ready_to_paste():
    checklist = build_checklist(_scheme("pmegp"))
    text = checklist["whatsapp_text"]
    assert "PMEGP" in text
    assert checklist["source_url"] in text
    assert checklist["last_verified_at"] in text
    assert "Aadhaar" in text


def test_hindi_checklist_translates_the_chrome_only():
    checklist = build_checklist(_scheme("mudra-kishore"), "hi")
    labels = " ".join(g["label"] for g in checklist["groups"])
    assert any("\u0900" <= ch <= "\u097f" for ch in labels)
    assert "à¤" not in labels
    assert "MUDRA" in checklist["scheme_name"]


def test_plan_is_deterministic():
    first = build_document_plan(MANUFACTURER, "", ["pmegp", "mudra-kishore"], "en")
    second = build_document_plan(MANUFACTURER, "", ["pmegp", "mudra-kishore"], "en")
    assert first == second


# ── endpoint ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_endpoint_returns_checklists(client):
    response = client.post("/api/documents", json={"intake": MANUFACTURER, "lang": "en"})
    assert response.status_code == 200
    body = response.json()
    assert body["checklists"]
    assert body["disclaimer"]
    assert all(c["groups"] for c in body["checklists"])


def test_endpoint_accepts_hindi(client):
    response = client.post("/api/documents", json={"intake": MANUFACTURER, "lang": "hi"})
    assert response.status_code == 200
    assert "à¤" not in response.text
