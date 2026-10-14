"""
P0 security & input-validation tests.

Covers:
- path traversal via client-controlled session_id (memory layer + WS + REST)
- WebSocket input validation (malformed JSON, unknown types, bad max_steps)
- API input caps (chat message length, session_id pattern, TTS text length)

Run from the repo root:  .venv\\Scripts\\python.exe -m pytest tests/ -q
"""
import urllib.parse
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TRAVERSAL_IDS = [
    "../data/schemes",        # resolves to backend/data/schemes.json (real file)
    "../../frontend/package", # resolves outside backend/ entirely
    "a/b/c",
    "..\\..\\windows",
    "s" * 65,                 # over the 64-char cap
    "has space",
    "semi;colon",
]


# ── memory layer ───────────────────────────────────────────────────────────

def test_memory_rejects_traversal_ids():
    from backend.core.memory import (
        clear_chat,
        delete_session,
        is_valid_session_id,
        load_chat_history,
        load_last_session,
        save_chat_message,
        save_session,
    )

    for bad_id in TRAVERSAL_IDS:
        assert not is_valid_session_id(bad_id)
        assert load_last_session(bad_id) is None
        assert load_chat_history(bad_id) == []
        with pytest.raises(ValueError):
            save_session(bad_id, "topic", {})
        with pytest.raises(ValueError):
            save_chat_message(bad_id, "user", "hi")
        with pytest.raises(ValueError):
            clear_chat(bad_id)
        with pytest.raises(ValueError):
            delete_session(bad_id)


def test_traversal_delete_cannot_touch_real_files():
    from backend.core.memory import delete_session

    target = Path(__file__).resolve().parent.parent / "backend" / "data" / "schemes.json"
    assert target.exists()
    with pytest.raises(ValueError):
        delete_session("../data/schemes")
    assert target.exists()


def test_valid_session_roundtrip():
    from backend.core.memory import (
        delete_session,
        is_valid_session_id,
        load_last_session,
        save_session,
    )

    sid = "s-1700000000000-abc123xy"
    assert is_valid_session_id(sid)
    save_session(sid, "tea stall", {"x": 1})
    try:
        loaded = load_last_session(sid)
        assert loaded and loaded["topic"] == "tea stall"
    finally:
        delete_session(sid)
    assert load_last_session(sid) is None


# ── HTTP surface ───────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_chat_rejects_oversized_message(client):
    r = client.post("/api/chat", json={"message": "x" * 4001})
    assert r.status_code == 422
    # Friendly, generic validation message — no internal field/error leakage.
    detail = r.json().get("detail")
    assert isinstance(detail, str) and len(detail) < 200


def test_chat_rejects_traversal_session_id(client):
    r = client.post("/api/chat", json={"message": "hi", "session_id": "../data/schemes"})
    assert r.status_code == 422


def test_chat_delete_rejects_traversal_session_id(client):
    # GDPR delete must refuse a bad session id, not silently report "cleared".
    r = client.delete("/api/chat/semi;colon")
    assert r.status_code == 422
    r2 = client.delete("/api/chat/ok-session_123")
    assert r2.status_code == 200
    assert r2.json() == {"status": "cleared", "session_id": "ok-session_123"}


def test_speak_rejects_oversized_text(client):
    r = client.post("/api/voice/speak", json={"text": "x" * 5001})
    assert r.status_code == 422


def test_get_session_traversal_is_404(client):
    sid = urllib.parse.quote("../data/schemes", safe="")
    r = client.get(f"/api/sessions/{sid}")
    assert r.status_code == 404


# ── WebSocket surface ──────────────────────────────────────────────────────

def test_ws_rejects_traversal_session_id(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "tea stall in Pune",
            "max_steps": 4,
            "session_id": "../data/schemes",
        })
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "session id" in msg["message"].lower()


def test_ws_delete_rejects_traversal_session_id(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "delete_session", "session_id": "../../secrets"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert "session id" in msg["message"].lower()


def test_ws_unknown_message_type(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "definitely-not-a-command"})
        msg = ws.receive_json()
        assert msg["type"] == "error"
        assert msg["message"] == "Unsupported message."


def test_ws_non_dict_message_rejected(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json(["not", "an", "object"])
        msg = ws.receive_json()
        assert msg["type"] == "error"


def test_ws_malformed_json_keeps_connection_open(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_text("{this is not json")
        msg = ws.receive_json()
        assert msg["type"] == "error"
        # connection must survive a bad frame
        ws.send_json({"type": "nope"})
        msg2 = ws.receive_json()
        assert msg2["type"] == "error"


def test_ws_non_numeric_max_steps_does_not_crash(client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "start", "topic": "   ", "max_steps": "abc"})
        msg = ws.receive_json()
        assert msg == {"type": "error", "message": "Topic is empty."}
