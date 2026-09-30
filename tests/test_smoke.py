"""
Smoke suite — fast, offline-safe, no real LLM calls.

Covers the offline guarantee tier (heuristics), the never-raise contracts
(voice, langchain fallback, whatsapp webhook) and route registration.
Run from the repo root:  .venv\\Scripts\\python.exe -m pytest tests/ -q
"""
import asyncio

import pytest
from fastapi.testclient import TestClient


# ── heuristics (deterministic, zero LLM) ──────────────────────────────────

def test_fallback_plan_returns_steps():
    from backend.core.heuristics import fallback_plan

    plan = fallback_plan("open a tea stall")
    assert isinstance(plan, list) and len(plan) >= 3
    assert all(isinstance(s, str) and s.strip() for s in plan)


def test_loan_ready_score_bounded():
    from backend.core.heuristics import compute_loan_ready_score

    score = compute_loan_ready_score({"business_summary": "tea stall"})
    assert isinstance(score, dict)
    total = score.get("total", score.get("score", 0))
    assert 0 <= total <= 100


def test_parse_advisory_json_tolerates_prose():
    from backend.core.heuristics import parse_advisory_json

    assert parse_advisory_json("not json at all {{{") is None
    data = parse_advisory_json('{"business_summary": "x"}')
    assert data and data["business_summary"] == "x"


def test_scheme_matching_returns_list():
    from backend.core.heuristics import extract_topic, match_schemes

    matches = match_schemes(extract_topic("street food cart"))
    assert isinstance(matches, list)


# ── llm_client session state ──────────────────────────────────────────────

def test_reset_session_state_zeroes_counter():
    from backend.core.llm_client import SESSION_TOKEN_USAGE, reset_session_state

    SESSION_TOKEN_USAGE["total"] = 999
    reset_session_state()
    assert SESSION_TOKEN_USAGE == {"input": 0, "output": 0, "total": 0}


# ── langchain adapter (offline fallback path, LLM failure injected) ───────

def test_langchain_chain_builds():
    lc = pytest.importorskip("langchain_core")
    from backend.core.langchain_adapter import build_advisory_chain

    chain = build_advisory_chain("You are a test advisor.", agent_hint="chat")
    assert hasattr(chain, "ainvoke")


def test_run_prompt_never_raises_on_llm_failure(monkeypatch):
    from backend.core import langchain_adapter as adapter

    async def _boom(*args, **kwargs):
        raise ValueError("all providers down")

    # run_prompt() imports call_llm locally from backend.core.llm_client,
    # so patching the source module is sufficient (and necessary).
    import backend.core.llm_client as llm_client

    monkeypatch.setattr(llm_client, "call_llm", _boom)
    reply = asyncio.run(
        adapter.run_prompt(None, "price my soap?", agent_hint="chat", max_tokens=50)
    )
    assert isinstance(reply, str) and len(reply) > 0


# ── voice contracts (never raise, empty sentinels) ────────────────────────

def test_voice_empty_inputs():
    from backend.core.voice import speech_to_text, text_to_speech

    assert asyncio.run(speech_to_text(b"")) == ""
    assert asyncio.run(text_to_speech("   ")) == b""


# ── HTTP surface ──────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_langchain_status(client):
    r = client.get("/api/langchain/status")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "web_search_tool" in body["tools"]


def test_whatsapp_verify_unconfigured(client):
    # No WHATSAPP_VERIFY_TOKEN in this env → documented 503, never 500.
    r = client.get("/api/whatsapp/webhook?hub.mode=subscribe&hub.verify_token=x&hub.challenge=123")
    assert r.status_code in (200, 403, 503)


def test_whatsapp_post_always_200(client):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [{
            "changes": [{
                "value": {
                    "messages": [{
                        "from": "15550001111",
                        "type": "text",
                        "text": {"body": "MUDRA loan kaise milega?"},
                    }]
                }
            }]
        }],
    }
    r = client.post("/api/whatsapp/webhook", json=payload)
    # 200 even with no creds/LLM: the brain falls back to heuristics, the
    # send is skipped gracefully.
    assert r.status_code == 200
    assert r.json()["status"] == "processed"
