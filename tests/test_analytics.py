"""
tests/test_analytics.py — WS-12 first-party analytics.

The point of these tests is the *refusal* behaviour: analytics must be a
count-of-events system and nothing more. Unknown names, free text, PII-ish keys
and malformed session ids are all rejected, so renaming a button can never leak
what a user typed.
"""
from datetime import datetime, timedelta, timezone

import pytest

from backend.core import analytics
from backend.core.analytics import (
    EVENT_ALLOWLIST,
    cleanup_analytics,
    record_events,
    sanitize_event,
    summarize,
)

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, "ANALYTICS_DIR", str(tmp_path / "analytics"))
    return tmp_path / "analytics"


# ── sanitisation (the refusal behaviour) ────────────────────────────────────


def test_only_allowlisted_event_names_are_kept():
    assert sanitize_event({"name": "research_start"})["name"] == "research_start"
    assert sanitize_event({"name": "definitely_not_an_event"}) is None
    assert sanitize_event({"name": 42}) is None
    assert sanitize_event("research_start") is None
    assert sanitize_event(None) is None


def test_props_allowlist_drops_everything_else():
    clean = sanitize_event(
        {
            "name": "page_view",
            "props": {
                "page": "/research",
                "lang": "hi",
                "free_text": "my name is Ramesh",
                "email": "a@b.com",
                "business": "I sell fruit near the bus stand",
            },
        }
    )
    assert clean["props"] == {"page": "/research", "lang": "hi"}


def test_props_are_type_checked_and_length_capped():
    clean = sanitize_event(
        {
            "name": "page_view",
            "props": {"page": "x" * 200, "count": "not-an-int", "score": 84.0},
        }
    )
    assert len(clean["props"]["page"]) == 40
    assert "count" not in clean["props"]  # wrong type → dropped
    assert clean["props"]["score"] == 84  # integral float → int


def test_boolean_is_not_stored_as_a_count():
    clean = sanitize_event({"name": "ledger_tick", "props": {"count": True}})
    assert "count" not in clean["props"]


def test_market_and_tracker_events_are_recordable():
    """The new WS-6/WS-8 surface events must survive the allowlist, or the
    funnel silently loses a step."""
    for name in ("market_view", "tracker_scheme_added", "tracker_alerts_saved"):
        clean = sanitize_event({"name": name, "props": {"dataset": "mandi_price", "scheme": "pmegp", "channel": "whatsapp"}})
        assert clean is not None, f"{name} is not on the allowlist"
        assert clean["name"] == name
        assert clean["props"]["dataset"] == "mandi_price"


# ── recording ───────────────────────────────────────────────────────────────


def test_record_events_writes_only_the_valid_rows(store):
    result = record_events(
        [
            {"name": "research_start", "props": {"lang": "en"}},
            {"name": "bogus"},
            {"name": "research_done", "props": {"status": "ok"}},
        ],
        session_id="abc-123",
        now=NOW,
    )
    assert result == {"accepted": 2, "rejected": 1}
    rows = analytics._read_day("2026-10-17")
    assert [r["name"] for r in rows] == ["research_start", "research_done"]
    assert all(r["session"] == "abc-123" for r in rows)


def test_a_malformed_session_id_is_never_stored(store):
    record_events([{"name": "page_view"}], session_id="../../etc/passwd", now=NOW)
    rows = analytics._read_day("2026-10-17")
    assert rows and "session" not in rows[0]


def test_summarize_counts_and_funnel_are_deterministic(store):
    for name in ("checkup_start", "checkup_start", "checkup_complete", "research_start"):
        record_events([{"name": name}], session_id="s1", now=NOW)

    report = summarize(days=7, now=NOW)
    assert report["total_events"] == 4
    assert report["unique_sessions"] == 1
    assert report["by_name"]["checkup_start"] == 2

    funnel = {step["step"]: step for step in report["funnel"]}
    assert funnel["checkup_start"]["count"] == 2
    assert funnel["checkup_start"]["rate"] == 1.0
    assert funnel["checkup_complete"]["rate"] == 0.5
    assert funnel["research_start"]["rate"] == 0.5
    assert funnel["research_done"]["count"] == 0
    assert funnel["research_done"]["rate"] == 0.0


def test_summarize_ignores_days_outside_the_window(store):
    record_events([{"name": "page_view"}], now=NOW)
    old = NOW - timedelta(days=10)
    record_events([{"name": "page_view"}], now=old)

    assert summarize(days=7, now=NOW)["total_events"] == 1
    assert summarize(days=30, now=NOW)["total_events"] == 2


def test_cleanup_removes_files_past_retention(store):
    record_events([{"name": "page_view"}], now=NOW)
    record_events([{"name": "page_view"}], now=NOW - timedelta(days=analytics.RETENTION_DAYS + 5))

    removed = cleanup_analytics(now=NOW)
    assert removed == 1


def test_record_never_raises_when_the_store_is_unwritable(store, monkeypatch):
    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("builtins.open", boom)
    result = record_events([{"name": "page_view"}], now=NOW)
    assert result["accepted"] == 0


# ── REST surface ────────────────────────────────────────────────────────────


def test_analytics_endpoints_round_trip():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/analytics/events",
            json={
                "session_id": "test-analytics",
                "events": [
                    {"name": "checkup_start", "props": {"page": "/research"}},
                    {"name": "not_a_real_event"},
                ],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["accepted"] == 1
        assert body["rejected"] == 1

        summary = client.get("/api/analytics/summary?days=7")
        assert summary.status_code == 200
        assert set(summary.json()["funnel"][0]) == {"step", "count", "rate"}

        # Out-of-range window is a friendly 422, not a crash.
        assert client.get("/api/analytics/summary?days=999").status_code == 422


def test_allowlist_is_not_accidentally_empty():
    assert "research_start" in EVENT_ALLOWLIST
    assert len(EVENT_ALLOWLIST) >= 10
