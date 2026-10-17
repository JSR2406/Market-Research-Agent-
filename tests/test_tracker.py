"""
tests/test_tracker.py — the application tracker, deadline calendar and alerts (WS-6).

Two things here would be actively harmful if they regressed, so they are pinned:
the "closing soon" flag is plain date arithmetic (a scheme "closing in 14 days"
must fire, 15 must not), and no deadline ever appears that we cannot point at a
URL for. A made-up closing date costs a user a wasted trip to a bank.
"""
import json
from datetime import date

import pytest

from backend.core import tracker

TODAY = date(2026, 10, 18)

INTAKE = {
    "business": "I make and sell candles in my home workshop",
    "offering": "decorative candles",
    "location": "Nagpur",
    "age": "3 years",
    "earnings": "40000 per month",
    "registered": "Yes, Udyam",
}


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Point the tracker at a throwaway session directory, never the real one."""
    monkeypatch.setattr(tracker, "SESSIONS_DIR", tmp_path)
    return tmp_path


# ── dates ─────────────────────────────────────────────────────────────────────


def test_parse_date_accepts_iso_and_rejects_everything_else():
    assert tracker.parse_date("2026-10-18") == date(2026, 10, 18)
    assert tracker.parse_date(date(2026, 10, 18)) == date(2026, 10, 18)
    for bad in ["", None, "18-10-2026", "tomorrow", "2026-13-01", 20261018]:
        assert tracker.parse_date(bad) is None


@pytest.mark.parametrize(
    "when,expected",
    [
        ("2026-10-17", tracker.STATE_LAPSED),   # yesterday
        ("2026-10-18", tracker.STATE_SOON),      # today still counts
        ("2026-11-01", tracker.STATE_SOON),      # exactly 14 days — the boundary
        ("2026-11-02", tracker.STATE_OPEN),      # 15 days
    ],
)
def test_deadline_state_boundaries(when, expected):
    state = tracker.deadline_state(when, TODAY)
    assert state["state"] == expected
    assert state["days_left"] == (tracker.parse_date(when) - TODAY).days


def test_deadline_state_flags_a_lapsed_pending_window_as_awaiting_confirmation():
    """A lapsed window with a proposed renewal is not 'closed'."""
    state = tracker.deadline_state("2026-09-30", TODAY, kind="window_pending")
    assert state["state"] == tracker.STATE_LAPSED_PENDING
    assert state["days_left"] == -18


def test_deadline_state_without_a_date_is_rolling():
    state = tracker.deadline_state(None, TODAY)
    assert state["state"] == tracker.STATE_ROLLING
    assert state["days_left"] is None


def test_deadline_state_speaks_hindi():
    assert tracker.deadline_state("2026-11-01", TODAY, lang="hi")["state_label"] == "जल्द बंद हो रहा है"


def test_window_is_configurable():
    assert tracker.deadline_state("2026-11-20", TODAY, window_days=40)["state"] == tracker.STATE_SOON
    assert tracker.deadline_state("2026-11-20", TODAY, window_days=14)["state"] == tracker.STATE_OPEN


# ── curated deadlines ─────────────────────────────────────────────────────────


def test_every_curated_deadline_carries_a_source_and_a_verified_date():
    rows = tracker.load_deadlines()
    assert rows, "the curated deadline file should not be empty"
    for row in rows:
        assert row["source_url"].startswith("http"), row
        assert tracker.parse_date(row["last_verified_at"]), row
        assert tracker.parse_date(row["date"]), row
        assert row["title"].get("en") and row["title"].get("hi"), row


def test_malformed_deadline_rows_are_dropped_not_guessed(tmp_path):
    path = tmp_path / "deadlines.json"
    path.write_text(
        json.dumps(
            [
                {"scheme_id": "a", "date": "2026-11-01", "title": {"en": "x"}},
                {"scheme_id": "b", "date": "not-a-date"},
                {"scheme_id": "c"},
                "nonsense",
            ]
        ),
        encoding="utf-8",
    )
    rows = tracker.load_deadlines(path)
    assert [row["scheme_id"] for row in rows] == ["a"]


def test_missing_deadline_file_is_an_empty_list(tmp_path):
    assert tracker.load_deadlines(tmp_path / "nope.json") == []


# ── applications ──────────────────────────────────────────────────────────────


def test_validate_application_fills_in_the_curated_details():
    row = tracker.validate_application({"scheme_id": "pmegp", "status": "docs_ready"})
    assert row["scheme_name"]
    assert row["tier_group"] == "pmegp"
    assert row["source_url"].startswith("http")
    assert row["status_label"] == "Documents ready"


def test_validate_application_rejects_an_unknown_scheme():
    with pytest.raises(ValueError):
        tracker.validate_application({"scheme_id": "made-up-scheme"})


def test_validate_application_rejects_an_unknown_status():
    with pytest.raises(ValueError):
        tracker.validate_application({"scheme_id": "pmegp", "status": "banana"})


def test_validate_application_rejects_a_non_iso_target_date():
    with pytest.raises(ValueError):
        tracker.validate_application({"scheme_id": "pmegp", "target_date": "30/10/2026"})


def test_validate_application_caps_notes():
    row = tracker.validate_application({"scheme_id": "pmegp", "notes": "x" * 900})
    assert len(row["notes"]) == tracker.MAX_NOTE_CHARS


def test_validate_applications_collapses_tiers_of_the_same_programme():
    rows = tracker.validate_applications(
        [
            {"scheme_id": "mudra-shishu"},
            {"scheme_id": "mudra-kishore"},
            {"scheme_id": "pmegp"},
        ]
    )
    ids = [row["scheme_id"] for row in rows]
    assert ids == ["mudra-shishu", "pmegp"]  # one MUDRA card, not four


def test_validate_applications_rejects_a_non_list_and_too_many():
    with pytest.raises(ValueError):
        tracker.validate_applications({"scheme_id": "pmegp"})
    with pytest.raises(ValueError):
        tracker.validate_applications([{"scheme_id": "pmegp"}] * (tracker.MAX_APPLICATIONS + 1))


def test_validate_applications_of_none_is_empty():
    assert tracker.validate_applications(None) == []


# ── the board ─────────────────────────────────────────────────────────────────


def test_board_without_a_tracker_lists_every_curated_deadline():
    board = tracker.build_board([], TODAY)
    assert {row["scheme_id"] for row in board["rows"]} >= {"pmfme", "pm-svanidhi"}
    assert all(row["state"] != tracker.STATE_ROLLING for row in board["rows"])


def test_board_adds_a_rolling_row_for_a_scheme_with_no_published_window():
    apps = tracker.validate_applications([{"scheme_id": "cgtmse"}])
    board = tracker.build_board(apps, TODAY)
    rolling = [row for row in board["rows"] if row["state"] == tracker.STATE_ROLLING]
    assert [row["scheme_id"] for row in rolling] == ["cgtmse"]
    assert "no closing date" in rolling[0]["title"].lower()


def test_board_shows_a_window_about_to_shut_even_if_it_is_untracked():
    """A window about to close is worth showing even if it is not on the list."""
    deadlines = [
        {
            "scheme_id": "pmegp",
            "kind": "window",
            "date": "2026-10-25",
            "title": {"en": "x", "hi": "x"},
            "note": {"en": "", "hi": ""},
            "source_url": "https://example.gov.in/x",
            "last_verified_at": "2026-10-18",
        }
    ]
    apps = tracker.validate_applications([{"scheme_id": "cgtmse"}])
    board = tracker.build_board(apps, TODAY, deadlines=deadlines)
    assert "pmegp" in {row["scheme_id"] for row in board["rows"]}


def test_board_hides_a_lapsed_window_for_an_untracked_scheme():
    apps = tracker.validate_applications([{"scheme_id": "cgtmse"}])
    board = tracker.build_board(apps, TODAY)
    assert "pmfme" not in {row["scheme_id"] for row in board["rows"]}


def test_board_shows_the_users_own_target_date():
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "target_date": "2026-10-30"}])
    board = tracker.build_board(apps, TODAY)
    mine = [row for row in board["rows"] if row["source"] == "yours"]
    assert len(mine) == 1
    assert mine[0]["state"] == tracker.STATE_SOON
    assert mine[0]["days_left"] == 12


def test_board_sorts_dated_rows_before_rolling_ones():
    apps = tracker.validate_applications(
        [{"scheme_id": "cgtmse"}, {"scheme_id": "pmegp", "target_date": "2026-10-30"}]
    )
    rows = tracker.build_board(apps, TODAY)["rows"]
    states = [row["state"] for row in rows]
    assert states[-1] == tracker.STATE_ROLLING
    dated = [row["date"] for row in rows if row["state"] != tracker.STATE_ROLLING]
    assert dated == sorted(dated)


def test_board_counts_and_closing_soon_filter():
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "target_date": "2026-10-30"}])
    board = tracker.build_board(apps, TODAY)
    assert [row["scheme_id"] for row in board["closing_soon"]] == ["pmegp"]
    assert board["counts"][tracker.STATE_SOON] == 1
    assert sum(board["counts"].values()) == len(board["rows"])


def test_board_is_deterministic_for_a_given_day():
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "target_date": "2026-10-30"}])
    assert tracker.build_board(apps, TODAY) == tracker.build_board(apps, TODAY)


def test_board_carries_a_localised_disclaimer():
    assert tracker.build_board([], TODAY, "hi")["disclaimer"] == tracker.DISCLAIMER["hi"]


# ── alerts ────────────────────────────────────────────────────────────────────


def test_alert_for_a_soon_target_is_the_users_own_date_wording():
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "target_date": "2026-10-30"}])
    board = tracker.build_board(apps, TODAY)
    alerts = tracker.build_alerts(apps, board, today=TODAY)
    soon = [m for m in alerts["messages"] if m["event"] == "deadline_soon"]
    assert len(soon) == 1
    assert "target date" in soon[0]["message"]
    assert "12" in soon[0]["message"]


def test_alert_mentions_a_scheme_window_that_is_closing():
    deadlines = [
        {
            "scheme_id": "pmegp",
            "kind": "window",
            "date": "2026-10-25",
            "title": {"en": "x", "hi": "x"},
            "note": {"en": "", "hi": ""},
            "source_url": "https://example.gov.in/x",
            "last_verified_at": "2026-10-18",
        }
    ]
    apps = tracker.validate_applications([{"scheme_id": "pmegp"}])
    board = tracker.build_board(apps, TODAY, deadlines=deadlines)
    alerts = tracker.build_alerts(apps, board, today=TODAY)
    message = [m for m in alerts["messages"] if m["event"] == "deadline_soon"][0]["message"]
    assert "window closes" in message


def test_alert_fires_when_our_record_was_re_verified_since_last_visit():
    apps = tracker.validate_applications([{"scheme_id": "pmegp"}])
    alerts = tracker.build_alerts(
        apps, None, previous_verified={"pmegp": "2020-01-01"}, today=TODAY
    )
    reverified = [m for m in alerts["messages"] if m["event"] == "reverified"]
    assert len(reverified) == 1
    assert "re-checked" in reverified[0]["message"]


def test_no_alert_when_nothing_changed():
    apps = tracker.validate_applications([{"scheme_id": "cgtmse"}])
    alerts = tracker.build_alerts(apps, None, today=TODAY)
    assert alerts["messages"] == []
    assert "Nothing needs your attention" in alerts["summary"]


def test_alert_suggests_a_newly_matched_scheme_from_the_intake():
    alerts = tracker.build_alerts([], None, intake=INTAKE, today=TODAY)
    matches = [m for m in alerts["messages"] if m["event"] == "new_match"]
    # Best-first and capped: a handful of nudges, never the whole catalogue
    # (plus a single "and N more" line when the list is truncated).
    assert 1 <= len(matches) <= tracker.MAX_NEW_MATCHES + 1


def test_alert_does_not_re_suggest_a_scheme_already_tracked():
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "status": "planning"}])
    alerts = tracker.build_alerts(apps, None, intake=INTAKE, today=TODAY)
    suggested = {m["scheme_id"] for m in alerts["messages"] if m["event"] == "new_match"}
    assert "pmegp" not in suggested


def test_new_match_nudges_are_one_per_programme_family():
    alerts = tracker.build_alerts([], None, intake=INTAKE, today=TODAY)
    ids = [m["scheme_id"] for m in alerts["messages"] if m["event"] == "new_match" and m["scheme_id"]]
    assert len(ids) == len(set(ids))


def test_alert_summary_speaks_hindi():
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "target_date": "2026-10-30"}])
    alerts = tracker.build_alerts(apps, None, today=TODAY, lang="hi")
    assert "आपकी तारीख़" in alerts["summary"]


# ── alert subscriptions ───────────────────────────────────────────────────────


def test_validate_alert_defaults_the_events_to_all_of_them():
    sub = tracker.validate_alert({"channel": "whatsapp", "value": "919876543210", "consent": True})
    assert sub["events"] == tracker.ALERT_EVENTS
    assert sub["consent"] is True


def test_validate_alert_requires_explicit_consent():
    with pytest.raises(ValueError):
        tracker.validate_alert({"channel": "whatsapp", "value": "919876543210"})


@pytest.mark.parametrize(
    "payload",
    [
        {"channel": "sms", "value": "919876543210", "consent": True},
        {"channel": "whatsapp", "value": "not-a-number", "consent": True},
        {"channel": "email", "value": "nope", "consent": True},
        {"channel": "whatsapp", "value": "919876543210", "consent": False},
    ],
)
def test_validate_alert_rejects_bad_payloads(payload):
    with pytest.raises(ValueError):
        tracker.validate_alert(payload)


def test_validate_alert_accepts_an_email_and_an_empty_opt_out():
    assert tracker.validate_alert({"channel": "email", "value": "a@b.in", "consent": True})["channel"] == "email"
    assert tracker.validate_alert(None) == {}


# ── persistence ───────────────────────────────────────────────────────────────


def test_tracker_round_trips_through_the_session_store(store):
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "target_date": "2026-10-30"}])
    alert = tracker.validate_alert({"channel": "whatsapp", "value": "919876543210", "consent": True})
    tracker.save_tracker("sess-1", apps, alert)
    loaded = tracker.load_tracker("sess-1")
    assert loaded["applications"][0]["scheme_id"] == "pmegp"
    assert loaded["alert"]["channel"] == "whatsapp"
    tracker.delete_tracker("sess-1")
    assert tracker.load_tracker("sess-1")["applications"] == []


def test_tracker_refuses_to_write_without_a_valid_session_id(store):
    with pytest.raises(ValueError):
        tracker.save_tracker("../escape", [])
    assert tracker.load_tracker("../escape")["applications"] == []


def test_tracker_file_keeps_devanagari_readable(store):
    """Encoding discipline: raw UTF-8 on disk, not \\u escapes."""
    apps = tracker.validate_applications([{"scheme_id": "pmegp", "notes": "बैंक शाखा"}])
    tracker.save_tracker("sess-hi", apps, {})
    raw = (store / "sess-hi_tracker.json").read_text(encoding="utf-8")
    assert "बैंक शाखा" in raw


# ── REST surface ──────────────────────────────────────────────────────────────


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(tracker, "SESSIONS_DIR", tmp_path)
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_deadlines_endpoint_lists_curated_rows(client):
    body = client.get("/api/deadlines").json()
    assert body["deadlines"]
    assert body["disclaimer"]
    assert all(row["source_url"].startswith("http") for row in body["deadlines"])


def test_deadlines_endpoint_translates_the_disclaimer(client):
    assert client.get("/api/deadlines?lang=hi").json()["disclaimer"] == tracker.DISCLAIMER["hi"]


def test_tracker_endpoint_is_empty_for_a_fresh_session(client):
    body = client.get("/api/tracker/fresh-session").json()
    assert body["applications"] == []
    assert body["statuses"]
    assert {s["id"] for s in body["statuses"]} == set(tracker.STATUSES)


def test_tracker_endpoint_rejects_an_invalid_session_id(client):
    assert client.get("/api/tracker/bad..id").status_code == 422


def test_tracker_endpoint_saves_applications_and_reads_them_back(client):
    payload = {
        "applications": [{"scheme_id": "pmegp", "status": "submitted", "target_date": "2026-10-30"}],
        "lang": "en",
    }
    saved = client.post("/api/tracker/sess-api", json=payload)
    assert saved.status_code == 200
    body = saved.json()
    assert body["applications"][0]["status"] == "submitted"
    assert body["board"]["rows"]  # a board came back with the save
    again = client.get("/api/tracker/sess-api").json()
    assert again["applications"][0]["scheme_id"] == "pmegp"
    assert again["applications"][0]["target_date"] == "2026-10-30"


def test_tracker_endpoint_rejects_an_unknown_scheme_with_a_sentence(client):
    resp = client.post("/api/tracker/sess-x", json={"applications": [{"scheme_id": "nope"}]})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and "{" not in detail and "Traceback" not in detail


def test_tracker_endpoint_rejects_an_alert_without_consent(client):
    resp = client.post(
        "/api/tracker/sess-y",
        json={
            "applications": [{"scheme_id": "pmegp"}],
            "alert": {"channel": "whatsapp", "value": "919876543210"},
        },
    )
    assert resp.status_code == 422


def test_tracker_endpoint_persists_an_alert_and_previews_it(client):
    resp = client.post(
        "/api/tracker/sess-alert",
        json={
            "applications": [{"scheme_id": "pmegp", "target_date": "2026-10-30"}],
            "alert": {"channel": "email", "value": "a@b.in", "events": ["deadline_soon"], "consent": True},
            "lang": "en",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["alert"]["channel"] == "email"


def test_deleting_a_session_also_deletes_its_tracker(store, monkeypatch):
    """GDPR right-to-delete must sweep the sibling tracker file too."""
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", store)
    tracker.save_tracker("sess-del", tracker.validate_applications([{"scheme_id": "pmegp"}]), {})
    assert (store / "sess-del_tracker.json").exists()
    memory.delete_session("sess-del")
    assert not (store / "sess-del_tracker.json").exists()
