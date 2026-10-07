"""
Additional E2E cases for Phase 29: invalid inputs, malformed frames,
export/delete, session resume edge cases, and chat profile injection.
"""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def llm_forced_down():
    import importlib

    mods = ["planner", "research", "analyst", "opportunity", "writer", "editor", "simplifier", "chat"]
    modules = [importlib.import_module(f"backend.agents.{name}") for name in mods]
    saved = {m: m.call_llm for m in modules}

    async def _boom(*args, **kwargs):
        raise RuntimeError("down")

    for m in modules:
        m.call_llm = _boom
    yield
    for m, fn in saved.items():
        m.call_llm = fn


@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def _run_ws(client, topic, profile="", max_steps=1, session_id=""):
    events = []
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": topic,
            "profile": profile,
            "max_steps": max_steps,
            "session_id": session_id,
        })
        for _ in range(40):
            ev = ws.receive_json()
            events.append(ev)
            if ev.get("type") in ("done", "cancelled", "error"):
                break
    return events


def test_invalid_session_id_start_rejected(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "start", "topic": "tea stall", "session_id": "../evil"})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert ev["message"] == "Invalid session id."


def test_invalid_session_id_export_rejected(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "export_session", "session_id": "bad/../../id"})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert ev["message"] == "Invalid session id."


def test_invalid_session_id_delete_rejected(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "delete_session", "session_id": "bad id"})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert ev["message"] == "Invalid session id."


def test_malformed_frame_emits_friendly_error(llm_forced_down, client):
    from starlette.testclient import TestClient

    # Send non-JSON text frame via raw websocket
    with client.websocket_connect("/ws/market") as ws:
        ws.send_text("not json")
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert "could not be read" in ev["message"].lower()


def test_unsupported_message_type_emits_error(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "unknown_command"})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert ev["message"] == "Unsupported message."


def test_export_session_not_found_emits_error(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "export_session", "session_id": "nope123"})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert "no saved session found" in ev["message"].lower()


def test_delete_session_success_emits_event(llm_forced_down, client):
    sid = "deltest123"
    _run_ws(client, "kirana shop", max_steps=1, session_id=sid)
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "delete_session", "session_id": sid})
        ev = ws.receive_json()
        assert ev["type"] == "session_deleted"
        assert ev["session_id"] == sid


def test_chat_with_profile_injection(llm_forced_down, client):
    r = client.post("/api/chat", json={
        "message": "tell me about loans for my business",
        "profile": "I run a kirana shop in Delhi",
        "lang": "en"
    })
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body.get("session_id") is not None


def test_chat_input_capped_422(llm_forced_down, client):
    r = client.post("/api/chat", json={"message": "x" * 5000})
    assert r.status_code == 422


def test_chat_invalid_session_422(llm_forced_down, client):
    r = client.post("/api/chat", json={"message": "hi", "session_id": "../bad"})
    assert r.status_code == 422