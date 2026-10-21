"""
tests/test_history.py — the session history layer and the schemes API.

The history layer is the one place where a refactor can silently destroy user
data: a session used to hold a single advisory, and the newest run must never
erase the ones before it. These tests pin the additive contract — runs are kept
newest-first and capped, the latest run is still readable in the legacy shape,
facts are derived deterministically, and the read-only REST surface keeps the
scheme dataset and the run history in sync.
"""
import pytest
from fastapi.testclient import TestClient

from backend.core.memory import (
    MAX_RUNS_PER_SESSION,
    delete_session,
    get_runs_list,
    get_session_facts,
    load_last_session,
    load_latest_run,
    load_pending_gate_summary,
    load_run,
    record_gate_decision,
    save_session,
    save_session_gate,
    update_session_state,
)


def _state(topic: str, *, business: str = "tea stall", amount: int = 50000, score: int = 60):
    return {
        "plan": ["research demand", "match schemes"],
        "final_report": '{"business_summary": "%s"}' % topic,
        "simplified_report": "simple " + topic,
        "eligibility": {"business_class": "retail", "business_label": "Retail", "amount": amount},
        "ledger": {"completed": ["a"], "score": score},
        "profile": "Business profile: " + topic,
        "intake": {"business": business, "location": "Pune"},
        "sources": [{"title": "ref", "url": "https://example.com"}],
        "token_usage": {"input": 1, "output": 2},
        "engine": "test",
    }


def test_runs_are_kept_newest_first_and_capped():
    sid = "test-history-runs"
    try:
        for i in range(MAX_RUNS_PER_SESSION + 2):
            save_session(sid, f"topic-{i}", _state(f"topic-{i}"))
        session = load_last_session(sid)
        assert len(session["runs"]) == MAX_RUNS_PER_SESSION
        # Newest first.
        assert session["runs"][0]["topic"] == f"topic-{MAX_RUNS_PER_SESSION + 1}"
        # The legacy latest-state mirror is the newest run.
        assert session["state"]["final_report"] == '{"business_summary": "topic-%d"}' % (MAX_RUNS_PER_SESSION + 1)
    finally:
        delete_session(sid)


def test_save_appends_runs_instead_of_overwriting():
    sid = "test-history-append"
    try:
        save_session(sid, "first", _state("first"))
        save_session(sid, "second", _state("second"))
        session = load_last_session(sid)
        assert [r["topic"] for r in session["runs"]] == ["second", "first"]
        # Top-level topic mirrors the newest.
        assert session["topic"] == "second"
    finally:
        delete_session(sid)


def test_facts_are_derived_and_merged_forward():
    sid = "test-history-facts"
    try:
        save_session(sid, "first", _state("first", business="tea stall", amount=50000, score=60))
        facts = get_session_facts(sid)
        assert facts["business_type"] == "tea stall"
        assert facts["location"] == "Pune"
        assert facts["last_eligible_amount"] == 50000
        assert facts["last_loan_ready_score"] == 60

        # A later run updates overlapping facts without losing older ones.
        save_session(sid, "second", _state("second", business="dairy", amount=80000, score=75))
        facts = get_session_facts(sid)
        assert facts["business_type"] == "dairy"
        assert facts["last_eligible_amount"] == 80000
        assert facts["last_loan_ready_score"] == 75
    finally:
        delete_session(sid)


def test_update_session_state_does_not_add_a_run():
    sid = "test-history-update"
    try:
        save_session(sid, "only", _state("only", score=40))
        update_session_state(sid, {"ledger": {"completed": ["a", "b"], "score": 55}})
        session = load_last_session(sid)
        assert len(session["runs"]) == 1, "ticking the ledger must not add a phantom run"
        assert session["runs"][0]["ledger"]["score"] == 55
        assert get_session_facts(sid)["last_loan_ready_score"] == 55
    finally:
        delete_session(sid)


def test_load_run_and_get_runs_list():
    sid = "test-history-load-run"
    try:
        save_session(sid, "one", _state("one"))
        save_session(sid, "two", _state("two"))

        runs = get_runs_list(sid)
        assert len(runs) == 2
        assert runs[0]["topic"] == "two"
        assert runs[0]["has_report"] is True
        assert runs[0]["eligibility"]["amount"] == 50000
        assert runs[0]["loan_ready_score"] == 60

        run_id = load_last_session(sid)["runs"][1]["run_id"]
        one = load_run(sid, run_id)
        assert one is not None
        assert one["topic"] == "one"
        assert one["state"]["final_report"] == '{"business_summary": "one"}'

        # Unknown run id is simply absent.
        assert load_run(sid, "nope") is None
    finally:
        delete_session(sid)


def test_legacy_single_run_file_is_migrated():
    """A pre-history file must open without losing its advisory."""
    import json

    from backend.core.memory import SESSIONS_DIR, _session_file

    sid = "test-history-legacy"
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    legacy = {
        "session_id": sid,
        "topic": "old business",
        "state": _state("old business"),
        "updated_at": 1700000000.0,
    }
    _session_file(sid).write_text(json.dumps(legacy), encoding="utf-8")
    try:
        session = load_last_session(sid)
        assert len(session["runs"]) == 1
        assert session["runs"][0]["topic"] == "old business"
        # Facts were back-filled from the migrated run.
        assert get_session_facts(sid)["business_type"] == "tea stall"
        assert load_latest_run(sid)["state"]["final_report"] == '{"business_summary": "old business"}'
    finally:
        delete_session(sid)


# ── REST surface ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_schemes_endpoint_serves_curated_data(client):
    r = client.get("/api/schemes")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["schemes"]) >= 1
    for scheme in body["schemes"]:
        # Provenance is mandatory for every scheme the product shows.
        assert scheme.get("source_url")
        assert scheme.get("last_verified_at")

    # `/list` is an alias for the same data.
    r2 = client.get("/api/schemes/list")
    assert r2.status_code == 200
    assert r2.json()["count"] == body["count"]


def test_session_history_endpoints(client):
    sid = "test-history-rest"
    try:
        save_session(sid, "rest one", _state("rest one"))

        runs = client.get(f"/api/sessions/{sid}/runs")
        assert runs.status_code == 200
        run_list = runs.json()["runs"]
        assert len(run_list) == 1
        run_id = run_list[-1]["run_id"]

        detail = client.get(f"/api/sessions/{sid}/runs/{run_id}")
        assert detail.status_code == 200
        d = detail.json()
        assert d["topic"] == "rest one"
        assert d["final_report"] == '{"business_summary": "rest one"}'
        # The state calls it `ledger`; the run detail exposes it as action_ledger.
        assert d["action_ledger"]["score"] == 60

        facts = client.get(f"/api/sessions/{sid}/facts")
        assert facts.status_code == 200
        assert facts.json()["facts"]["business_type"] == "tea stall"
        assert facts.json()["intake"]["location"] == "Pune"
    finally:
        delete_session(sid)


def test_dashboard_shows_waiting_approval_and_chosen_scheme(client):
    """
    The history/dashboard view must reflect the gate, not just the reports.

    A parked run has no report, so the waiting gate is the only sign that a run
    is still the user's to decide. And a run that got through a scheme gate
    carries the scheme the user actually committed to.
    """
    sid = "test-history-dashboard"
    try:
        state = _state("gated run")
        state["scheme_choice"] = {
            "value": "mudra",
            "name": "MUDRA — Tarun",
            "status": "Eligible",
            "loan_ceiling": "₹10,00,000",
            "source_url": "https://www.mudra.org.in/",
            "last_verified_at": "2026-01-01",
            "is_none": False,
        }
        save_session(sid, "gated run", state)

        body = client.get(f"/api/sessions/{sid}/runs").json()
        listed = body["runs"][0]
        assert listed["scheme_choice"]["name"] == "MUDRA — Tarun"
        assert listed["scheme_choice"]["source_url"].startswith("https://")
        assert listed["scheme_choice"]["is_none"] is False
        # Nothing has been parked yet.
        assert body["pending_gate"] == {}

        run_id = listed["run_id"]
        detail = client.get(f"/api/sessions/{sid}/runs/{run_id}").json()
        assert detail["scheme_choice"]["name"] == "MUDRA — Tarun"

        # A decision that is still pending shows up on the dashboard.
        gate = {
            "gate_id": "gate-dashboard-1",
            "kind": "plan_approval",
            "status": "pending",
            "question": "May we go to the web?",
            "created_at": 123.0,
        }
        save_session_gate(sid, gate)
        pending = client.get(f"/api/sessions/{sid}/runs").json()["pending_gate"]
        assert pending["gate_id"] == "gate-dashboard-1"
        assert pending["question"] == "May we go to the web?"
        assert pending["status"] == "pending"

        # Once decided, the dashboard stops asking.
        record_gate_decision(sid, {"gate_id": "gate-dashboard-1", "decision": "approve"})
        assert client.get(f"/api/sessions/{sid}/runs").json()["pending_gate"] == {}
        assert load_pending_gate_summary(sid) == {}
    finally:
        delete_session(sid)


def test_pending_gate_summary_prefers_the_newest_pending_gate():
    sid = "test-history-pending-gates"
    try:
        save_session_gate(sid, {
            "gate_id": "old", "kind": "plan_approval", "status": "pending",
            "question": "old", "created_at": 10.0,
        })
        save_session_gate(sid, {
            "gate_id": "new", "kind": "scheme_approval", "status": "pending",
            "question": "new", "created_at": 20.0,
        })
        assert load_pending_gate_summary(sid)["gate_id"] == "new"

        # An unknown session has nothing waiting — never raises.
        assert load_pending_gate_summary("no-such-session") == {}
        assert load_pending_gate_summary("bad id") == {}
    finally:
        delete_session(sid)


def test_session_history_rejects_bad_ids(client):
    # A malformed id (fails the allowlist) is refused; a well-formed but unknown
    # session simply has no history yet.
    assert client.get("/api/sessions/bad id/facts").status_code == 404
    assert client.get("/api/sessions/bad id/runs").status_code == 404
    unknown = client.get("/api/sessions/unknown-session/runs")
    assert unknown.status_code == 200
    assert unknown.json()["runs"] == []


def test_session_export_and_delete_endpoints(client):
    """The UI's export/delete buttons ride on these two REST routes."""
    sid = "test-history-export"
    try:
        save_session(sid, "export me", _state("export me"))

        exp = client.get(f"/api/sessions/{sid}/export")
        assert exp.status_code == 200
        body = exp.json()
        assert body["session_id"] == sid
        assert body["run_count"] == 1
        assert body["runs"][0]["topic"] == "export me"
        assert body["facts"]["business_type"] == "tea stall"
        assert body["intake"]["location"] == "Pune"

        # An unknown (well-formed) session exports nothing.
        assert client.get("/api/sessions/nope-session/export").status_code == 404

        deleted = client.delete(f"/api/sessions/{sid}")
        assert deleted.status_code == 200
        assert deleted.json() == {"status": "deleted", "session_id": sid}

        # Gone afterwards — both the resume read and the export 404.
        assert client.get(f"/api/sessions/{sid}").status_code == 404
        assert client.get(f"/api/sessions/{sid}/export").status_code == 404
    finally:
        delete_session(sid)


def test_session_delete_rejects_bad_ids(client):
    assert client.delete("/api/sessions/bad id").status_code == 404
