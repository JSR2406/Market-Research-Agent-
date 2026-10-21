"""
test_gates.py — the human approval gate (S1).

The gate is the first step towards a stateful research/task agent: the run
stops, asks the user a question, and waits for an answer that is *persisted*
rather than held in a socket.

What this suite pins down:

  * the gate payload is deterministic and bounded (no model-written claims);
  * a decision is validated, capped and recorded on the session;
  * the run really stops at the gate and really continues after an approval;
  * a decline ends the run on purpose — no report, no silent approval;
  * a run that nobody answers parks on disk and can be resumed later;
  * right-to-delete takes the gate with it.
"""
import importlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.core.gates import (
    DECISION_APPROVE,
    DECISION_REJECT,
    GATE_APPROVED,
    GATE_PENDING,
    GATE_REJECTED,
    apply_decision,
    build_plan_gate,
    validate_decision,
)

LLM_MODULES = [
    "backend.core.llm_client",
    "backend.agentic.supervisor",
]


@pytest.fixture(scope="module", autouse=True)
def llm_forced_down():
    """Every provider down + no live web — offline, deterministic, fast."""
    from backend.agentic import tools as agentic_tools

    modules = [importlib.import_module(m) for m in LLM_MODULES]
    saved = {m: m.call_llm for m in modules}

    async def _boom(*args, **kwargs):
        raise RuntimeError("all LLM providers unavailable (test)")

    for m in modules:
        m.call_llm = _boom

    async def _no_web(query):
        return ""

    original_web = agentic_tools._web_search_async
    agentic_tools._web_search_async = _no_web
    agentic_tools.TOOLS["web_search"].afn = _no_web
    yield
    for m, fn in saved.items():
        m.call_llm = fn
    agentic_tools._web_search_async = original_web
    agentic_tools.TOOLS["web_search"].afn = original_web


@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


# ── the payload ──────────────────────────────────────────────────────────────

def test_gate_payload_is_deterministic_and_bounded():
    gate = build_plan_gate(
        lang="en",
        steps=["Look up the market"] * 20,
        schemes=[
            {
                "name": "MUDRA",
                "status_label": "Eligible",
                "source_url": "https://www.mudra.org.in/",
                "last_verified_at": "2026-01-01",
            }
        ] * 20,
    )
    assert gate["kind"] == "plan_approval"
    assert gate["status"] == GATE_PENDING
    assert gate["gate_id"].startswith("g-")
    assert len(gate["steps"]) <= 8
    assert len(gate["schemes"]) <= 6
    assert gate["schemes"][0]["source_url"] == "https://www.mudra.org.in/"
    assert gate["schemes"][0]["last_verified_at"] == "2026-01-01"
    # The options are fixed and localised, never model-written.
    assert [o["value"] for o in gate["options"]] == [DECISION_APPROVE, DECISION_REJECT]


def test_gate_speaks_the_users_language():
    en = build_plan_gate(lang="en")
    hi = build_plan_gate(lang="hi")
    assert en["question"] != hi["question"]
    assert hi["lang"] == "hi"
    # Official programme names are never translated — the gate text has none.
    for text in (en["question"], en["detail"], hi["question"], hi["detail"]):
        assert "MUDRA" not in text
        assert "PMEGP" not in text
        assert "Udyam" not in text


def test_decision_validation_rejects_junk():
    with pytest.raises(ValueError):
        validate_decision(None)
    with pytest.raises(ValueError):
        validate_decision({"gate_id": "", "decision": "approve"})
    with pytest.raises(ValueError):
        validate_decision({"gate_id": "g-1", "decision": "maybe"})
    with pytest.raises(ValueError):
        validate_decision({"gate_id": "g-1" * 100, "decision": "approve"})

    ok = validate_decision({"gate_id": "g-abc", "decision": "APPROVE", "note": " ok "})
    assert ok == {"gate_id": "g-abc", "decision": "approve", "note": "ok"}


def test_decision_note_is_capped():
    ok = validate_decision({"gate_id": "g-abc", "decision": "approve", "note": "x" * 5000})
    assert len(ok["note"]) == 500


def test_apply_decision_sets_the_status():
    gate = build_plan_gate()
    approved = apply_decision(gate, {"decision": DECISION_APPROVE, "note": "go"})
    assert approved["status"] == GATE_APPROVED
    assert approved["decided_at"]
    assert approved["note"] == "go"

    rejected = apply_decision(gate, {"decision": DECISION_REJECT, "note": "no"})
    assert rejected["status"] == GATE_REJECTED


# ── persistence ──────────────────────────────────────────────────────────────

def test_gate_survives_on_the_session(tmp_path, monkeypatch):
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", tmp_path)
    sid = "gate_persist_session"

    gate = build_plan_gate()
    memory.save_session_gate(sid, gate, topic="kirana shop", intake={"business": "kirana shop"})

    stored = memory.load_session_gate(sid)
    assert stored["gate_id"] == gate["gate_id"]
    assert stored["status"] == GATE_PENDING

    session = memory.load_last_session(sid)
    assert session["topic"] == "kirana shop"
    assert session["intake"] == {"business": "kirana shop"}
    # A parked gate is not a run — the history must stay clean.
    assert session["runs"] == []

    updated = memory.record_gate_decision(
        sid, {"gate_id": gate["gate_id"], "decision": DECISION_APPROVE, "note": ""}
    )
    assert updated["status"] == GATE_APPROVED
    assert memory.load_session_gate(sid)["status"] == GATE_APPROVED

    # A decision for a gate that is not this one changes nothing.
    other = memory.record_gate_decision(
        sid, {"gate_id": "g-somethingelse", "decision": DECISION_REJECT, "note": ""}
    )
    assert other == {}
    assert memory.load_session_gate(sid)["status"] == GATE_APPROVED


def test_right_to_delete_takes_the_gate_with_it(tmp_path, monkeypatch):
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", tmp_path)
    sid = "gate_delete_session"
    memory.save_session_gate(sid, build_plan_gate(), topic="kirana shop")

    memory.delete_session(sid)
    assert memory.load_session_gate(sid) == {}


def test_invalid_session_id_cannot_write_a_gate(tmp_path, monkeypatch):
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", tmp_path)
    with pytest.raises(ValueError):
        memory.save_session_gate("../escape", build_plan_gate())
    assert memory.load_session_gate("../escape") == {}


# ── the run itself ───────────────────────────────────────────────────────────

def _read_until(ws, wanted, limit=200):
    """Read events until one of ``wanted`` arrives; return (event, seen)."""
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event)
        if event.get("type") in wanted:
            return event, seen
    return None, seen


def test_run_waits_for_approval_and_continues(client):
    """The gate stops the run; approving it lets the report through."""
    sid = "gate_ws_approve"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
            "gates": True,
        })
        pending, seen = _read_until(ws, {"gate_pending"})
        assert pending is not None, seen
        gate = pending["gate"]
        assert gate["status"] == GATE_PENDING
        assert gate["question"]
        assert gate["detail"]
        # No research happened before the approval.
        assert "done" not in [e.get("type") for e in seen]

        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": gate["gate_id"],
            "decision": "approve",
        })

        decided, seen2 = _read_until(ws, {"done", "error", "gate_paused"})
        assert decided is not None, seen2
        assert decided["type"] == "done", seen2
        report = json.loads(decided["final_report"])
        assert report["business_summary"]

    from backend.core.memory import delete_session, load_last_session

    session = load_last_session(sid)
    assert session["runs"] and session["runs"][0]["final_report"]
    assert session["gate"]["status"] == GATE_APPROVED
    delete_session(sid)


def test_declining_the_gate_ends_the_run_on_purpose(client):
    """A decline is not a failure and not an approval: the run stops."""
    sid = "gate_ws_reject"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
            "gates": True,
        })
        pending, seen = _read_until(ws, {"gate_pending"})
        assert pending is not None, seen
        gate = pending["gate"]

        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": gate["gate_id"],
            "decision": "reject",
        })

        paused, seen2 = _read_until(ws, {"gate_paused", "done", "error"})
        assert paused is not None, seen2
        assert paused["type"] == "gate_paused", seen2
        assert paused["status"] == GATE_REJECTED
        assert "done" not in [e.get("type") for e in seen2]

    from backend.core.memory import delete_session, load_last_session

    session = load_last_session(sid)
    # Nothing was produced, so nothing was saved as a run.
    assert session["runs"] == []
    assert session["gate"]["status"] == GATE_REJECTED
    delete_session(sid)


def test_an_unanswered_gate_parks_and_can_be_resumed(client, monkeypatch):
    """Nobody answers in time → the run parks on disk and can be resumed."""
    import backend.agentic.nodes as agentic_nodes

    monkeypatch.setattr(agentic_nodes, "GATE_WAIT_SECONDS", 1)
    sid = "gate_ws_resume"

    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
            "gates": True,
        })
        pending, seen = _read_until(ws, {"gate_pending"})
        assert pending is not None, seen
        gate = pending["gate"]

        paused, seen2 = _read_until(ws, {"gate_paused"})
        assert paused is not None, seen2
        assert paused["type"] == "gate_paused"
        assert paused["status"] == GATE_PENDING
        assert "done" not in [e.get("type") for e in seen2]

        # The gate is on disk, so the user can come back later.
        from backend.core.memory import load_last_session

        parked = load_last_session(sid)
        assert parked["gate"]["gate_id"] == gate["gate_id"]
        assert parked["gate"]["status"] == GATE_PENDING
        assert parked["topic"]
        assert parked["runs"] == []

        # Approving it now resumes the run with the same intake.
        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": gate["gate_id"],
            "decision": "approve",
        })
        done, seen3 = _read_until(ws, {"done", "error", "gate_paused"})
        assert done is not None, seen3
        assert done["type"] == "done", seen3
        assert json.loads(done["final_report"])["business_summary"]

    from backend.core.memory import delete_session

    delete_session(sid)


def test_gates_are_off_unless_the_run_asks_for_them(client):
    """Default behaviour is unchanged: no gate, no extra round trip."""
    sid = "gate_ws_off"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
        })
        done, seen = _read_until(ws, {"done", "error", "gate_pending"})
        assert done is not None, seen
        assert done["type"] == "done", seen
        assert "gate_pending" not in [e.get("type") for e in seen]

    from backend.core.memory import delete_session

    delete_session(sid)


def test_a_bad_decision_is_answered_friendly(client):
    sid = "gate_ws_bad"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "gate_decision", "session_id": sid, "gate_id": "g-x", "decision": "maybe"})
        event = ws.receive_json()
        assert event["type"] == "error"
        assert "could not be read" in event["message"]

        # An unknown session id is refused too.
        ws.send_json({
            "type": "gate_decision",
            "session_id": "../escape",
            "gate_id": "g-x",
            "decision": "approve",
        })
        event = ws.receive_json()
        assert event["type"] == "error"
        assert event["message"] == "Invalid session id."


# ── finding the gate again ───────────────────────────────────────────────────

def test_a_parked_gate_is_findable_after_a_reload(client, tmp_path, monkeypatch):
    """The gate outlives the tab: the user can find it and decide it later."""
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", tmp_path)
    sid = "gate_reload_session"
    gate = build_plan_gate()
    memory.save_session_gate(sid, gate, topic="kirana shop", intake={"business": "kirana shop"})

    res = client.get(f"/api/sessions/{sid}/gate")
    assert res.status_code == 200
    body = res.json()
    assert body["gate"]["gate_id"] == gate["gate_id"]
    assert body["gate"]["status"] == GATE_PENDING
    assert body["topic"] == "kirana shop"
    assert body["intake"] == {"business": "kirana shop"}

    # A session with no gate reports nothing to decide.
    assert client.get("/api/sessions/gate_no_such_session/gate").status_code == 404
    # And a hostile id never reaches the disk.
    assert client.get("/api/sessions/..%2Fescape/gate").status_code == 404


def test_a_new_run_clears_the_stale_gate(client, tmp_path, monkeypatch):
    """A fresh run means a fresh gate — a stale approval cannot resume it."""
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", tmp_path)
    sid = "gate_stale_session"
    memory.save_session_gate(sid, build_plan_gate(), topic="kirana shop")

    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
        })
        done, seen = _read_until(ws, {"done", "error", "gate_pending"})
        assert done is not None, seen
        assert done["type"] == "done", seen

    assert memory.load_session_gate(sid) == {}
    memory.delete_session(sid)
