"""
tests/test_provenance.py — WS-7 freshness arithmetic.

These tests pin the *pure* part of provenance: given a ``last_verified_at`` and a
clock, when does a curated record stop being presented as current? The rules are
deterministic on purpose — a scheme must never look "verified" just because a
network job failed to run.
"""
from datetime import datetime, timedelta, timezone

from backend.core.provenance import (
    REVIEW_CADENCE_DAYS,
    annotate_schemes,
    provenance_block,
    review_dates,
    source_host,
    staleness_report,
)

NOW = datetime(2026, 10, 17, tzinfo=timezone.utc)


def _days_ago(days: int) -> str:
    return (NOW - timedelta(days=days)).date().isoformat()


# ── date arithmetic ─────────────────────────────────────────────────────────


def test_a_recent_record_is_fresh():
    dates = review_dates(_days_ago(1), now=NOW)
    assert dates["freshness"] == "fresh"
    assert dates["is_stale"] is False
    assert dates["days_left"] > 0


def test_a_record_past_its_cadence_is_stale():
    dates = review_dates(_days_ago(REVIEW_CADENCE_DAYS + 1), now=NOW)
    assert dates["freshness"] == "stale"
    assert dates["is_stale"] is True
    assert dates["days_left"] < 0


def test_a_record_near_its_review_date_is_due_soon():
    dates = review_dates(_days_ago(REVIEW_CADENCE_DAYS - 3), now=NOW)
    assert dates["freshness"] == "due_soon"
    assert dates["is_stale"] is False


def test_an_unreadable_date_is_unknown_and_treated_as_stale():
    for bad in (None, "", "not-a-date", "08/10/2026"):
        dates = review_dates(bad, now=NOW)
        assert dates["freshness"] == "unknown"
        assert dates["is_stale"] is True, bad


def test_review_window_is_derived_from_the_cadence():
    dates = review_dates("2026-01-01", now=NOW)
    assert dates["as_of"] == "2026-01-01"
    expected = (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=REVIEW_CADENCE_DAYS)).date()
    assert dates["next_review"] == expected.isoformat()


# ── source host ─────────────────────────────────────────────────────────────


def test_source_host_strips_www_and_handles_junk():
    assert source_host("https://www.mudra.org.in/") == "mudra.org.in"
    assert source_host("https://pmegp.gov.in/scheme") == "pmegp.gov.in"
    assert source_host("") == ""


# ── provenance block ────────────────────────────────────────────────────────


def test_a_sourced_fresh_scheme_carries_a_verifiable_block():
    block = provenance_block(
        {"source_url": "https://www.mudra.org.in/", "last_verified_at": _days_ago(2)},
        now=NOW,
    )
    assert block["has_source"] is True
    assert block["source_host"] == "mudra.org.in"
    assert block["freshness"] == "fresh"
    assert block["label"].startswith("verified ")


def test_a_scheme_without_a_source_is_labelled_unsourced():
    block = provenance_block({"source_url": "", "last_verified_at": _days_ago(1)}, now=NOW)
    assert block["has_source"] is False
    assert block["label"] == "unsourced"


# ── dataset-level behaviour ─────────────────────────────────────────────────


def test_annotate_preserves_every_existing_key():
    source = [{"id": "x", "scheme_name": "X", "source_url": "https://example.gov.in", "last_verified_at": _days_ago(1)}]
    out = annotate_schemes(source, now=NOW)
    assert out[0]["id"] == "x"
    assert out[0]["scheme_name"] == "X"
    assert "provenance" in out[0]
    # The input must not be mutated — annotate is a pure copy.
    assert "provenance" not in source[0]


def test_staleness_report_partitions_every_record_once():
    schemes = [
        {"id": "fresh", "source_url": "https://a.gov.in", "last_verified_at": _days_ago(1)},
        {"id": "soon", "source_url": "https://b.gov.in", "last_verified_at": _days_ago(REVIEW_CADENCE_DAYS - 2)},
        {"id": "stale", "source_url": "https://c.gov.in", "last_verified_at": _days_ago(400)},
        {"id": "unsourced", "source_url": "", "last_verified_at": _days_ago(1)},
        {"id": "unknown", "source_url": "https://d.gov.in", "last_verified_at": "nonsense"},
    ]
    report = staleness_report(schemes, now=NOW)
    assert report["total"] == 5
    assert report["stale"] == ["stale"]
    assert report["due_soon"] == ["soon"]
    assert report["unsourced"] == ["unsourced"]
    assert report["unknown"] == ["unknown"]

    listed = report["stale"] + report["due_soon"] + report["unsourced"] + report["unknown"]
    # Every non-fresh record lands in exactly one bucket; `fresh` is the rest.
    assert sorted(listed) == ["soon", "stale", "unknown", "unsourced"]
    assert report["fresh"] == 1


def test_the_shipped_dataset_is_fully_sourced():
    """Every curated scheme must carry a source URL — no exceptions.

    Freshness may legitimately drift (a record can be 'due_soon'), but a record
    with *no* source can never be shown as a government fact. This is the guard
    that keeps a future edit from quietly dropping provenance.
    """
    from backend.core.heuristics import load_schemes

    schemes = load_schemes()
    assert schemes, "the curated dataset must not be empty"
    report = staleness_report(schemes, now=NOW)
    assert report["unsourced"] == [], report["unsourced"]
    assert report["unknown"] == [], report["unknown"]


# ── REST surface ────────────────────────────────────────────────────────────


def test_schemes_endpoint_exposes_provenance_and_health():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        listing = client.get("/api/schemes")
        assert listing.status_code == 200
        body = listing.json()
        assert body["count"] >= 1
        for scheme in body["schemes"]:
            block = scheme.get("provenance")
            assert block, "every served scheme must carry a provenance block"
            assert block["has_source"] is True
            assert block["source_host"]
            assert block["freshness"] in {"fresh", "due_soon", "stale", "unknown"}

        health = client.get("/api/schemes/health")
        assert health.status_code == 200
        summary = health.json()
        assert summary["total"] == body["count"]
        assert summary["unsourced"] == []


# ── verification job (WS-7) — pure helpers only, no network ─────────────────


def test_content_signature_is_stable_and_content_sensitive():
    from backend.jobs.verify_sources import content_signature

    assert content_signature("") == ""
    assert content_signature("abc") == content_signature("abc")
    assert content_signature("abc") != content_signature("abd")


def test_assess_classifies_every_outcome():
    from backend.jobs.verify_sources import assess

    prev_same = {"signature": "sig", "reachable": True}
    assert assess({"reachable": False, "signature": ""}, prev_same) == "dead"
    assert assess({"reachable": True, "signature": "sig"}, None) == "new"
    assert assess({"reachable": True, "signature": "other"}, prev_same) == "changed"
    assert assess({"reachable": True, "signature": "sig"}, prev_same) == "ok"


def test_promotion_requires_unchanged_content_and_a_prior_signature():
    from backend.jobs.verify_sources import should_promote

    assert should_promote("ok", True) is True
    assert should_promote("ok", False) is False  # first fetch is not a verification
    assert should_promote("changed", True) is False
    assert should_promote("dead", True) is False


def test_apply_promotions_selects_only_unchanged_verified_records():
    from backend.jobs.verify_sources import apply_promotions

    schemes = [
        {"id": "a", "last_verified_at": "2026-01-01"},
        {"id": "b", "last_verified_at": "2026-01-01"},
        {"id": "c", "last_verified_at": "2026-10-17"},
    ]
    health = {
        "a": {"assessment": "ok", "previous_signature": "x"},
        "b": {"assessment": "changed", "previous_signature": "x"},
        "c": {"assessment": "ok", "previous_signature": "x"},
    }
    promoted = apply_promotions(schemes, health, today="2026-10-17")
    assert promoted == ["a"]  # b changed, c already today

