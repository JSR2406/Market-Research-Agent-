"""
tests/test_intake.py — the Business Check-up intake layer.

Covers the deterministic parts only: normalization (untrusted client input),
the canonical snippet, gap detection, and the business-type-aware follow-up
question. No LLM is involved, so these run offline like the rest of the suite.

The HTTP and run-level tests at the bottom pin the *wiring*: the structured
intake must reach the advisor chat and the research run, and nothing an
untrusted client sends may leak past normalize_intake().
"""
import asyncio
import re
from pathlib import Path

import pytest

from backend.core.intake import (
    FIELD_IDS,
    MAX_VALUE_CHARS,
    build_intake_snippet,
    describe_missing,
    followup_instruction,
    is_intake_complete,
    missing_fields,
    next_question,
    normalize_intake,
)

FRONTEND_INTAKE = Path(__file__).resolve().parents[1] / "frontend" / "lib" / "intake.ts"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_normalize_drops_unknown_ids_and_junk():
    raw = {
        "business": "fruit cart",
        "not_a_field": "ignore me",
        "earnings": "   ",
        "location": 42,
        "need": "  more   customers  ",
    }
    out = normalize_intake(raw)
    assert out == {"business": "fruit cart", "need": "more customers"}
    assert "not_a_field" not in out
    assert "earnings" not in out  # blank == unanswered


def test_normalize_caps_value_length_and_collapses_whitespace():
    out = normalize_intake({"business": "a" * 900 + "\n\n  b"})
    assert len(out["business"]) <= MAX_VALUE_CHARS
    assert "\n" not in out["business"]


def test_normalize_survives_non_dict_input():
    assert normalize_intake(None) == {}
    assert normalize_intake(["business"]) == {}
    assert normalize_intake("business=fruit") == {}


def test_build_snippet_is_canonical_and_capped():
    snippet = build_intake_snippet({"business": "fruit cart", "location": "Nagpur"})
    assert snippet.startswith("Business profile — ")
    assert "your business: fruit cart" in snippet
    assert "location: Nagpur" in snippet
    # Idempotent — re-building from the same answers is stable.
    assert build_intake_snippet({"business": "fruit cart"}) == (
        "Business profile — your business: fruit cart"
    )
    assert build_intake_snippet({}) == ""
    assert build_intake_snippet({"unknown": "x"}) == ""


def test_gap_priority_prefers_business_identity():
    assert missing_fields({})[0] == "business"
    assert missing_fields({"business": "fruit cart"})[0] == "offering"
    assert is_intake_complete({}) is False
    full = {fid: "x" for fid in FIELD_IDS}
    assert is_intake_complete(full) is True
    assert missing_fields(full) == []
    assert followup_instruction(full) == ""
    assert describe_missing(full) == ""


def test_next_question_adapts_to_the_business_type():
    farm = {"business": "Farm / dairy"}
    assert "grow" in next_question(farm, "en").lower()

    service = {"business": "Service / repair"}
    assert "service" in next_question(service, "en").lower()

    shop = {"business": "Shop / stall", "offering": "vegetables"}
    # `offering` is answered, so the next gap moves on to the money question.
    assert missing_fields(shop)[0] == "earnings"
    assert "month" in next_question(shop, "en").lower()


def test_next_question_is_localised():
    farm = {"business": "Farm / dairy"}
    hi = next_question(farm, "hi")
    assert re.search(r"[\u0900-\u097F]", hi), "Hindi question must be in Devanagari"
    assert re.search(r"[A-Za-z]", next_question(farm, "en"))


def test_product_words_do_not_make_saathi_ask_farming_questions():
    """
    Regression: "goat milk soap from my home" is a home-based producer, not a
    farmer. The adaptive question must not ask them what they grow.
    """
    soap = {"business": "I make and sell goat milk soap from my home in Pune"}
    question = next_question(soap, "en")
    assert "grow" not in question.lower()
    assert "sell" in question.lower()

    dairy = {"business": "I run a dairy farm with 8 cows"}
    assert "grow" in next_question(dairy, "en").lower()


def test_scale_question_is_land_specific_for_farmers():
    # Everything ahead of `scale` in the priority order answered, so the next
    # question is the size question — worded for the business already described.
    filled = {
        "business": "Farm / dairy",
        "offering": "milk",
        "earnings": "18,000",
        "location": "Nashik, Maharashtra",
        "age": "3–12 months",
        "loan": "No, first time",
        "need": "Money to grow",
    }
    assert missing_fields(filled)[0] == "scale"
    assert "land" in next_question(filled, "en").lower()

    shop = {**filled, "business": "Shop / stall", "offering": "vegetables"}
    assert "sell" in next_question(shop, "en").lower()


def test_followup_instruction_names_the_missing_detail():
    note = followup_instruction({"business": "fruit cart"}, "en")
    assert "NOT yet told you" in note
    assert "What exactly do you sell or do?" in note
    assert note.count("?") >= 1

    hi_note = followup_instruction({"business": "fruit cart"}, "hi")
    assert "नहीं बताया" in hi_note


def test_describe_missing_lists_a_few_fields():
    text = describe_missing({}, "en")
    assert text.startswith("Still to tell me: ")
    assert "your business" in text


def test_frontend_and_backend_field_ids_agree():
    """
    The frontend stepper and the backend canonicaliser must speak the same
    field ids, otherwise answers are silently dropped. Mirrors of each other,
    so pin the contract here.
    """
    source = FRONTEND_INTAKE.read_text(encoding="utf-8")
    block = re.search(
        r"export const INTAKE_QUESTIONS[^=]*=\s*\[(.*?)\n\];", source, re.DOTALL
    )
    assert block, "INTAKE_QUESTIONS registry not found in frontend/lib/intake.ts"
    frontend_ids = re.findall(r'id:\s*"([a-z_]+)"', block.group(1))
    assert frontend_ids == list(FIELD_IDS), (
        "frontend/lib/intake.ts ids drifted from backend/core/intake.py"
    )


# ── wiring: the intake must reach both surfaces ──────────────────────────────


def test_chat_api_uses_structured_intake_and_asks_for_the_gaps(client, monkeypatch):
    from backend.agents import chat as chat_mod
    from backend.core.memory import delete_session
    import backend.core.llm_client as llm_client

    captured: dict = {}

    async def _fake_llm(messages, **kwargs):
        captured["messages"] = messages
        return "Here is your tailored next step."

    monkeypatch.setattr(llm_client, "call_llm", _fake_llm)
    sid = "test-intake-chat-session"
    try:
        r = client.post(
            "/api/chat",
            json={
                "message": "mujhe loan chahiye",
                "session_id": sid,
                "intake": {"business": "Shop / stall", "not_a_field": "drop me"},
            },
        )
        assert r.status_code == 200
        assert r.json()["reply"] == "Here is your tailored next step."
        joined = " ".join(m["content"] for m in captured["messages"])
        # The canonical snippet is built from the structured answers...
        assert "Business Check-up intake answers" in joined
        assert "your business: Shop / stall" in joined
        # ...and the still-missing detail is asked for, deterministically.
        assert "NOT yet told you" in joined
        assert "What exactly do you sell or do?" in joined
        # Untrusted keys never reach a prompt.
        assert "not_a_field" not in joined
        assert "drop me" not in joined
    finally:
        delete_session(sid)


def test_chat_api_falls_back_to_the_intake_saved_with_the_run(client, monkeypatch):
    from backend.agents import chat as chat_mod
    from backend.core.memory import delete_session, save_session
    import backend.core.llm_client as llm_client

    sid = "test-intake-saved-session"
    save_session(
        sid,
        "fruit stall",
        {
            "intake": {"business": "Street vendor / cart", "location": "Nagpur"},
            "profile": build_intake_snippet({"business": "Street vendor / cart", "location": "Nagpur"}),
            "final_report": "{}",
        },
    )
    captured: dict = {}

    async def _fake_llm(messages, **kwargs):
        captured["messages"] = messages
        return "ok"

    monkeypatch.setattr(llm_client, "call_llm", _fake_llm)
    try:
        r = client.post("/api/chat", json={"message": "what next?", "session_id": sid})
        assert r.status_code == 200
        joined = " ".join(m["content"] for m in captured["messages"])
        assert "your business: Street vendor / cart" in joined
        assert "location: Nagpur" in joined
    finally:
        delete_session(sid)


def test_chat_api_rejects_oversized_intake(client):
    """A hostile client cannot smuggle a huge blob through the intake object."""
    r = client.post(
        "/api/chat",
        json={
            "message": "hello",
            "intake": {"business": "x" * 5000},
            "session_id": "",
        },
    )
    assert r.status_code == 200  # capped, not fatal
    assert len(normalize_intake({"business": "x" * 5000})["business"]) <= MAX_VALUE_CHARS


def test_workflow_folds_intake_into_topic_and_persists_it(monkeypatch):
    import backend.workflows.executor as ex
    from backend.agentic import nodes as nodes_mod
    from backend.agentic import supervisor as supervisor_mod
    from backend.agentic import tools as tools_mod
    from backend.core.memory import delete_session, load_last_session

    sid = "test-intake-workflow-session"
    captured: dict = {}

    class _FakeWS:
        def __init__(self):
            self.events = []

        async def send_json(self, payload):
            self.events.append(payload)

    async def _boom(*args, **kwargs):
        raise RuntimeError("LLM down (test)")

    async def _planner(topic, previous_context="", agent_hint=None):
        captured["planner_topic"] = topic
        return ["research fruit stall demand"]

    async def _research(task, agent_hint=None, live_context=None):
        return "local findings"

    async def _schemes(task, agent_hint=None):
        return "scheme text"

    async def _writer(task, agent_hint=None):
        captured["writer_task"] = task
        return '{"business_summary": "fruit stall"}'

    async def _editor(task, agent_hint=None):
        return '{"business_summary": "fruit stall"}'

    async def _simplifier(advisory_json, topic=""):
        return "plain summary"

    monkeypatch.setattr(nodes_mod, "call_llm", _boom)
    monkeypatch.setattr(supervisor_mod, "call_llm", _boom)

    async def _no_web(query):
        return ""

    monkeypatch.setattr(tools_mod.TOOLS["web_search"], "afn", _no_web)
    monkeypatch.setattr(nodes_mod, "planner_agent", _planner)
    monkeypatch.setattr(nodes_mod, "research_agent", _research)
    monkeypatch.setattr(nodes_mod, "opportunity_agent", _schemes)
    monkeypatch.setattr(nodes_mod, "writer_agent", _writer)
    monkeypatch.setattr(nodes_mod, "editor_agent", _editor)
    monkeypatch.setattr(nodes_mod, "simplifier_agent", _simplifier)

    ws = _FakeWS()
    intake = {
        "business": "Street vendor / cart",
        "offering": "seasonal fruits and vegetables",
        "location": "Nagpur, Maharashtra",
        "junk_field": "must not survive",
    }
    try:
        asyncio.run(
            ex.run_research_workflow(
                "I sell fruit on a cart",
                1,
                ws,
                {"cancelled": False},
                session_id=sid,
                intake=intake,
            )
        )
        # The user's own words reach planning and synthesis.
        assert "seasonal fruits and vegetables" in captured["planner_topic"]
        assert "Nagpur, Maharashtra" in captured["planner_topic"]
        assert "seasonal fruits and vegetables" in captured["writer_task"]
        assert "junk_field" not in captured["planner_topic"]

        # Persisted as structured intake so the chat can resume from it.
        saved = load_last_session(sid)
        assert saved["runs"][0]["intake"]["offering"] == "seasonal fruits and vegetables"
        assert "junk_field" not in saved["runs"][0]["intake"]
        assert ws.events[-1]["type"] == "done"
    finally:
        delete_session(sid)