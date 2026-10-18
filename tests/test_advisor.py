"""
tests/test_advisor.py — advisor / CA workspace (WS-11).

Covers auth, client CRUD, per-client + bulk eligibility, notes, reports and —
critically — cross-advisor isolation. Every isolation test is run twice: once
through the API and once against the raw repository, proving advisor A can
never touch advisor B's data.

The advisor repository writes JSON files under backend/sessions/advisor/. Each
test gets a private temp directory so runs are hermetic and offline.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.core.advisor as advisor_repo
from backend.main import app

# ── hermetic storage --------------------------------------------------------

@pytest.fixture
def advisor_dir(monkeypatch):
    """Point the advisor repository at a throwaway dir for this test."""
    tmp = Path(tempfile.mkdtemp(prefix="advisor-test-"))
    advisor_root = tmp / "advisor"
    for name in ("advisors", "sessions", "clients", "notes", "snapshots", "reports"):
        (advisor_root / name).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(advisor_repo, "ADVISOR_DIR", advisor_root)
    monkeypatch.setattr(advisor_repo, "_ADVISORS", advisor_root / "advisors")
    monkeypatch.setattr(advisor_repo, "_SESSIONS", advisor_root / "sessions")
    monkeypatch.setattr(advisor_repo, "_CLIENTS", advisor_root / "clients")
    monkeypatch.setattr(advisor_repo, "_NOTES", advisor_root / "notes")
    monkeypatch.setattr(advisor_repo, "_SNAPSHOTS", advisor_root / "snapshots")
    monkeypatch.setattr(advisor_repo, "_REPORTS", advisor_root / "reports")
    yield advisor_root
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def client(advisor_dir):
    with TestClient(app) as c:
        yield c


# ── helpers -----------------------------------------------------------------

def signup_raw(c: TestClient, email: str, password: str = "Secret1234", name: str = "A"):
    return c.post("/api/advisor/auth/signup", json={
        "email": email, "password": password, "name": name,
    })


def signup(c: TestClient, email: str, password: str = "Secret1234", name: str = "A"):
    r = signup_raw(c, email, password, name)
    assert r.status_code == 200, r.text
    return r.json()


def login(c: TestClient, email: str, password: str = "Secret1234"):
    r = c.post("/api/advisor/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def signin(c: TestClient, email: str, password: str = "Secret1234", name: str = "A"):
    """Sign up (if needed) then sign in; returns the login body with a token."""
    signup_raw(c, email, password, name)  # 422 if already exists — that's fine
    return login(c, email, password)


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def make_client_profile() -> dict:
    return {
        "label": "Sharma Kirana Store",
        "sector": "retail",
        "state": "MH",
        "stage": "operating",
        "profile": {
            "business": "kirana store",
            "offering": "groceries and staples",
            "scale": "small",
            "age": "3 years",
            "earnings": "₹25,000/month",
            "location": "Pune, Maharashtra",
            "loan": "no, first time",
            "need": "working capital",
            "registered": "yes, registered",
        },
    }


# ── auth ────────────────────────────────────────────────────────────────────

def test_signup_login_me_logout(client):
    signup(client, "alice@example.com")
    body = signin(client, "alice@example.com")
    assert body["email"] == "alice@example.com"
    assert body["token"], "login must return a bearer token"

    r = client.get("/api/advisor/auth/me", headers=auth_header(body["token"]))
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["id"] == body["id"]
    assert me["email"] == "alice@example.com"

    r = client.post("/api/advisor/auth/logout", headers=auth_header(body["token"]))
    assert r.status_code == 200

    # token is revoked
    r = client.get("/api/advisor/auth/me", headers=auth_header(body["token"]))
    assert r.status_code == 401


def test_signup_duplicate_email(client):
    assert signup_raw(client, "bob@example.com").status_code == 200
    assert signup_raw(client, "bob@example.com").status_code == 422


def test_all_advisor_routes_are_401_without_token(client):
    for method, path, body in [
        ("get", "/api/advisor/clients", None),
        ("post", "/api/advisor/clients", make_client_profile()),
        ("post", "/api/advisor/eligibility/bulk", {"client_ids": []}),
        ("post", "/api/advisor/reports", {"kind": "single", "client_ids": [], "locale": "en"}),
    ]:
        if method == "get":
            r = client.get(path)
        else:
            r = getattr(client, method)(path, json=body)
        assert r.status_code == 401, f"{method.upper()} {path} must be 401, got {r.status_code}"


# ── clients CRUD ────────────────────────────────────────────────────────────

def test_client_crud(client):
    token = signin(client, "alice@example.com")["token"]
    headers = auth_header(token)

    # create
    r = client.post("/api/advisor/clients", json=make_client_profile(), headers=headers)
    assert r.status_code == 200, r.text
    client_a = r.json()
    assert client_a["label"] == "Sharma Kirana Store"
    assert client_a["readiness"] is None  # not matched yet

    # list
    r = client.get("/api/advisor/clients", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["clients"]) == 1

    # get
    r = client.get(f"/api/advisor/clients/{client_a['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["id"] == client_a["id"]

    # update
    r = client.patch(f"/api/advisor/clients/{client_a['id']}", json={
        "label": "Sharma Kirana Store (updated)",
    }, headers=headers)
    assert r.status_code == 200
    assert r.json()["label"] == "Sharma Kirana Store (updated)"

    # delete
    r = client.delete(f"/api/advisor/clients/{client_a['id']}", headers=headers)
    assert r.status_code == 200
    r = client.get(f"/api/advisor/clients/{client_a['id']}", headers=headers)
    assert r.status_code == 404


def test_client_list_filters(client):
    token = signin(client, "alice@example.com")["token"]
    headers = auth_header(token)
    p1 = make_client_profile(); p1["label"] = "Alpha Store"; p1["sector"] = "retail"
    p2 = make_client_profile(); p2["label"] = "Beta Weaving"; p2["sector"] = "textiles"
    client.post("/api/advisor/clients", json=p1, headers=headers)
    client.post("/api/advisor/clients", json=p2, headers=headers)

    r = client.get("/api/advisor/clients?q=alpha", headers=headers)
    assert len(r.json()["clients"]) == 1
    assert r.json()["clients"][0]["label"] == "Alpha Store"

    r = client.get("/api/advisor/clients?sector=textiles", headers=headers)
    assert len(r.json()["clients"]) == 1
    assert r.json()["clients"][0]["label"] == "Beta Weaving"


# ── isolation (denial) ──────────────────────────────────────────────────────

def test_isolation_client_read_update_delete(client):
    """Advisor B cannot read/update/delete advisor A's client via the API."""
    tok_a = signin(client, "alice@example.com")["token"]
    tok_b = signin(client, "bob@example.com", name="B")["token"]
    ha, hb = auth_header(tok_a), auth_header(tok_b)

    r = client.post("/api/advisor/clients", json=make_client_profile(), headers=ha)
    assert r.status_code == 200
    client_id = r.json()["id"]

    # B reads A's client -> 404 (existence not leaked)
    r = client.get(f"/api/advisor/clients/{client_id}", headers=hb)
    assert r.status_code == 404
    # B updates A's client -> 404
    r = client.patch(f"/api/advisor/clients/{client_id}", json={"label": "hacked"},
                     headers=hb)
    assert r.status_code == 404
    # B deletes A's client -> 404
    r = client.delete(f"/api/advisor/clients/{client_id}", headers=hb)
    assert r.status_code == 404
    # A still owns it
    r = client.get(f"/api/advisor/clients/{client_id}", headers=ha)
    assert r.status_code == 200


def test_isolation_client_list_excludes_other_advisor(client):
    """B's client list never contains A's clients."""
    tok_a = signin(client, "alice@example.com")["token"]
    tok_b = signin(client, "bob@example.com", name="B")["token"]
    ha, hb = auth_header(tok_a), auth_header(tok_b)

    client.post("/api/advisor/clients", json=make_client_profile(), headers=ha)
    client.post("/api/advisor/clients", json=make_client_profile(), headers=hb)

    r = client.get("/api/advisor/clients", headers=ha)
    assert len(r.json()["clients"]) == 1
    r = client.get("/api/advisor/clients", headers=hb)
    assert len(r.json()["clients"]) == 1


def test_isolation_notes(client):
    tok_a = signin(client, "alice@example.com")["token"]
    tok_b = signin(client, "bob@example.com", name="B")["token"]
    ha, hb = auth_header(tok_a), auth_header(tok_b)

    r = client.post("/api/advisor/clients", json=make_client_profile(), headers=ha)
    client_id = r.json()["id"]

    # A adds a note
    r = client.post(f"/api/advisor/clients/{client_id}/notes", json={"body": "follow up"},
                    headers=ha)
    assert r.status_code == 200
    note_id = r.json()["id"]

    # B reads A's notes -> empty (client not found for B, so no notes)
    r = client.get(f"/api/advisor/clients/{client_id}/notes", headers=hb)
    assert r.status_code == 404

    # B deletes A's note -> 404
    r = client.delete(f"/api/advisor/notes/{note_id}", headers=hb)
    assert r.status_code == 404

    # A deletes own note -> 200
    r = client.delete(f"/api/advisor/notes/{note_id}", headers=ha)
    assert r.status_code == 200


def test_isolation_repository_layer(advisor_dir):
    """Direct repository calls are scoped by advisor_id (no HTTP involved)."""
    a = advisor_repo.create_advisor(email="a@example.com", password="p1", name="A")
    b = advisor_repo.create_advisor(email="b@example.com", password="p2", name="B")

    c = advisor_repo.create_client(a["id"], label="Client A",
                                   profile={"business": "tea stall"})
    # B's repository handle cannot see A's client
    assert advisor_repo.get_client(b["id"], c["id"]) is None
    assert advisor_repo.list_clients(b["id"]) == []
    # B cannot add a note on A's client
    assert advisor_repo.add_note(b["id"], c["id"], "x") is None
    # B cannot delete A's client
    assert advisor_repo.delete_client_cascade(b["id"], c["id"]) is False
    # A can
    assert advisor_repo.get_client(a["id"], c["id"]) is not None


# ── eligibility: per-client match + bulk ────────────────────────────────────

def test_match_creates_snapshot_and_readiness(client):
    tok = signin(client, "alice@example.com")["token"]
    h = auth_header(tok)
    r = client.post("/api/advisor/clients", json=make_client_profile(), headers=h)
    client_id = r.json()["id"]

    r = client.post(f"/api/advisor/clients/{client_id}/match", json={
        "topic": "working capital loan",
        "lang": "en",
    }, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client_id"] == client_id
    assert body["snapshot_id"]
    assert isinstance(body["ranked"], list)

    # readiness cached on the client
    r = client.get(f"/api/advisor/clients/{client_id}", headers=h)
    assert r.status_code == 200
    assert isinstance(r.json()["readiness"], int)
    assert 0 <= r.json()["readiness"] <= 100


def test_match_deterministic(client):
    """Same profile -> same ranked result set on re-run."""
    tok = signin(client, "alice@example.com")["token"]
    h = auth_header(tok)
    r = client.post("/api/advisor/clients", json=make_client_profile(), headers=h)
    client_id = r.json()["id"]

    def ranked_names():
        r = client.post(f"/api/advisor/clients/{client_id}/match", json={
            "topic": "working capital loan", "lang": "en",
        }, headers=h)
        return [m.get("scheme_id", "") for m in r.json()["ranked"]]

    first = ranked_names()
    second = ranked_names()
    assert first == second


def test_bulk_match_returns_ranked_per_client(client):
    tok = signin(client, "alice@example.com")["token"]
    h = auth_header(tok)
    profiles = [make_client_profile(), make_client_profile()]
    profiles[0]["label"] = "Client One"
    profiles[1]["label"] = "Client Two"
    ids = []
    for p in profiles:
        r = client.post("/api/advisor/clients", json=p, headers=h)
        ids.append(r.json()["id"])

    r = client.post("/api/advisor/eligibility/bulk", json={"client_ids": ids}, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine_version"] == "elig-1.0.0"
    assert len(body["results"]) == 2
    for res in body["results"]:
        assert res["label"] in ("Client One", "Client Two")
        assert isinstance(res["matches"], list)


def test_bulk_match_drops_unowned_ids(client):
    """clientIds owned by another advisor are omitted, never leaked."""
    tok_a = signin(client, "alice@example.com")["token"]
    tok_b = signin(client, "bob@example.com", name="B")["token"]
    ha, hb = auth_header(tok_a), auth_header(tok_b)

    # A creates a client; B creates a client
    ra = client.post("/api/advisor/clients", json=make_client_profile(), headers=ha)
    rb = client.post("/api/advisor/clients", json=make_client_profile(), headers=hb)
    a_id, b_id = ra.json()["id"], rb.json()["id"]

    # A bulk-matches [a_id, b_id] -> only a_id appears
    r = client.post("/api/advisor/eligibility/bulk",
                    json={"client_ids": [a_id, b_id]}, headers=ha)
    assert r.status_code == 200
    result_ids = [res["client_id"] for res in r.json()["results"]]
    assert a_id in result_ids
    assert b_id not in result_ids  # B's client not leaked to A


# ── reports ─────────────────────────────────────────────────────────────────

def test_report_generate_list_download(client):
    tok = signin(client, "alice@example.com")["token"]
    h = auth_header(tok)
    r = client.post("/api/advisor/clients", json=make_client_profile(), headers=h)
    client_id = r.json()["id"]
    client.post(f"/api/advisor/clients/{client_id}/match", json={"topic": "loan", "lang": "en"},
                headers=h)

    # combined report
    r = client.post("/api/advisor/reports", json={
        "kind": "combined", "client_ids": [client_id], "locale": "en",
    }, headers=h)
    assert r.status_code == 200, r.text
    report = r.json()
    assert report["kind"] == "combined"
    assert report["client_ids"] == [client_id]
    assert report["locale"] == "en"

    # list reports
    r = client.get("/api/advisor/reports", headers=h)
    assert r.status_code == 200
    assert len(r.json()["reports"]) == 1

    # get report metadata -> pdf_url present
    r = client.get(f"/api/advisor/reports/{report['id']}", headers=h)
    assert r.status_code == 200
    assert "pdf_url" in r.json()

    # download the PDF
    r = client.get(f"/api/advisor/reports/{report['id']}/pdf", headers=h)
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF"), "downloaded file must be a real PDF"

    # B cannot download A's report
    tok_b = signin(client, "bob@example.com", name="B")["token"]
    r = client.get(f"/api/advisor/reports/{report['id']}/pdf", headers=auth_header(tok_b))
    assert r.status_code == 404


# ── analytics events fire ───────────────────────────────────────────────────

def test_advisor_analytics_events(client):
    """advisor_client_added / bulk_match_run / advisor_report_generated are logged."""
    tok = signin(client, "alice@example.com")["token"]
    h = auth_header(tok)

    client.post("/api/advisor/clients", json=make_client_profile(), headers=h)
    r = client.get("/api/advisor/clients", headers=h)
    cid = r.json()["clients"][0]["id"]
    client.post("/api/advisor/eligibility/bulk", json={"client_ids": [cid]}, headers=h)
    client.post("/api/advisor/reports", json={
        "kind": "single", "client_ids": [cid], "locale": "en",
    }, headers=h)

    # Read today's analytics file and confirm the events are recorded.
    from backend.core.analytics import _today, _read_day
    rows = _read_day(_today())
    names = {row["name"] for row in rows}
    assert "advisor_client_added" in names
    # this test's bulk run reported exactly one client
    assert any(row["name"] == "bulk_match_run" and row["props"].get("clientCount") == 1
               for row in rows)
    assert "advisor_report_generated" in names
    # No PII: props carry ids/counts only (never names, emails, phones)
    for row in rows:
        props = row.get("props") or {}
        assert "email" not in props and "phone" not in props and "name" not in props
