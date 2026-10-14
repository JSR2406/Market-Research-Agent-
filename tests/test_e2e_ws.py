"""
E2E QA suite — the full WebSocket research pipeline against the real app,
with every LLM provider forced DOWN so it runs fast, offline and deterministically
through the heuristic guarantee tier (the exact experience a user gets when
Ollama/HF/OpenRouter are unreachable).

Covers, per persona (street vendor, kirana, tailor, home food business, dairy
farmer, repair shop, freelancer, new founder):
  - WS start -> graph -> plan -> node_start/node_end/token_usage -> done
  - final_report parses with the canonical advisory keys + loan_ready_score
  - matched_schemes contain a parseable, cited scheme line
  - simplified_report is present
  - the session persists (resume contract)

Also covers: empty topic, cancel mid-run, one agent failing (partial research),
offline advisor chat, and scheme-less topics still yielding a done advisory.
"""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

# Every module that calls the LLM directly (agents + the agentic router/critic).
LLM_MODULES = [
    "backend.agents.planner",
    "backend.agents.research",
    "backend.agents.analyst",
    "backend.agents.opportunity",
    "backend.agents.writer",
    "backend.agents.editor",
    "backend.agents.simplifier",
    "backend.agents.chat",
    "backend.agentic.supervisor",
    "backend.agentic.nodes",
]

PERSONAS = [
    # (topic, profile snippet, expected flask fragment of a matched scheme)
    (
        "I sell vegetables from a street cart near my home in Mumbai and earn about 12,000 rupees a month.",
        "street vendor / cart business",
        "SVANidhi",
    ),
    (
        "I run a small kirana shop and want to buy new stock to expand.",
        "shop or stall based business",
        "Kishore",
    ),
    (
        "I am a tailor and need a machine loan to buy a new sewing machine.",
        "home based service business",
        "CGTMSE",
    ),
    (
        "I am starting a home based food business selling tiffin to nearby offices.",
        "new business",
        "Shishu",
    ),
    (
        "I am a dairy farmer with 3 cows and want a loan to buy feed and a chaff cutter.",
        "farm / dairy / agriculture business",
        "MUDRA",
    ),
    (
        "I own a mobile repair shop and need money for tools and spare parts.",
        "shop or stall based business",
        "Kishore",
    ),
    (
        "I am a freelance designer earning about 40000 rupees per month and want to grow.",
        "service business from home",
        "MUDRA",
    ),
    (
        "I am starting a new delivery service business in my town.",
        "new business",
        "Shishu",
    ),
]


@pytest.fixture(scope="module", autouse=True)
def llm_forced_down():
    """Point every LLM caller's local call_llm reference at a hard failure,
    and neutralize live web so the whole suite runs offline + deterministically."""
    import importlib

    from backend.agentic import tools as agentic_tools

    modules = [importlib.import_module(m) for m in LLM_MODULES]
    saved = {m: m.call_llm for m in modules}

    async def _boom(*args, **kwargs):
        raise RuntimeError("all LLM providers unavailable (test)")

    for m in modules:
        m.call_llm = _boom

    async def _no_web(query):  # no network in tests
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


def _run_ws(client, topic, profile="", max_steps=2, session_id=""):
    """Drive one full run, returning the ordered event list."""
    events = []
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": topic,
            "profile": profile,
            "max_steps": max_steps,
            "session_id": session_id,
        })
        for _ in range(140):
            event = ws.receive_json()
            events.append(event)
            if event.get("type") in ("done", "cancelled", "error"):
                break
    return events


def _advisory(events):
    done = next(e for e in events if e.get("type") == "done")
    return json.loads(done["final_report"]), done


# ── personas across the full flow ──────────────────────────────────────────

@pytest.mark.parametrize("topic,profile,expect_scheme", PERSONAS,
                         ids=[f"p{i}" for i in range(len(PERSONAS))])
def test_persona_full_flow(llm_forced_down, client, topic, profile, expect_scheme):
    from backend.core.memory import delete_session, load_last_session

    sid = f"e2e_persona_{PERSONAS.index((topic, profile, expect_scheme))}"
    try:
        events = _run_ws(client, topic, profile=profile, max_steps=2, session_id=sid)
        types = [e["type"] for e in events]

        # The pipeline must always reach a terminal state we can render.
        assert "error" not in types, events
        assert "cancelled" not in types
        assert types[-1] == "done"
        assert "plan" in types
        assert "node_start" in types
        assert "token_usage" in types

        advisory, done = _advisory(events)
        for key in ("business_summary", "cash_flow_snapshot", "matched_schemes",
                    "documents_needed", "next_step"):
            assert key in advisory, f"missing key {key}"
        assert "loan_ready_score" in advisory
        score = advisory["loan_ready_score"]
        assert 0 <= score["score"] <= 100

        # Heuristic tier must propose a relevant scheme for these personas.
        assert advisory["matched_schemes"], "no schemes matched offline"
        joined = " ".join(advisory["matched_schemes"])
        assert expect_scheme.lower() in joined.lower(), f"expected {expect_scheme} in {joined}"
        # Scheme lines are cited (official source, verified date).
        assert "Source:" in joined and "verified" in joined

        assert done["simplified_report"], "simplified report missing"
        # Session persists for resume + advisor follow-ups.
        saved = load_last_session(sid)
        assert saved and saved["state"].get("final_report")
    finally:
        delete_session(sid)


def test_offline_advisor_chat_answers_with_schemes(llm_forced_down, client):
    r = client.post("/api/chat", json={"message": "which scheme fits my kirana shop?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert "Kishore" in body["reply"] or "MUDRA" in body["reply"]


# ── error & edge scenarios ─────────────────────────────────────────────────

def test_empty_topic_emits_friendly_error(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "start", "topic": "   "})
        ev = ws.receive_json()
        assert ev["type"] == "error"
        assert ev["message"] == "Topic is empty."  # friendly, no stack
        # Connection stays open — a valid message still works.
        ws.send_json({"type": "start", "topic": "tea stall", "max_steps": 1})
        seen = []
        for _ in range(140):
            t = ws.receive_json()["type"]
            seen.append(t)
            if t in ("done", "error", "cancelled"):
                break
        assert "done" in seen or "error" in seen


def test_cancel_stops_run_and_sends_no_done(llm_forced_down, client):
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({"type": "start", "topic": "tailor shop", "max_steps": 6})
        seen = []
        cancelled = False
        for _ in range(40):
            ev = ws.receive_json()
            seen.append(ev["type"])
            if ev["type"] == "node_start":
                ws.send_json({"type": "cancel", "session_id": ""})
            if ev["type"] == "cancelled":
                cancelled = True
                break
        assert cancelled, f"cancelled event missing; saw {seen}"
        assert "done" not in seen


def test_no_matching_scheme_still_produces_done(llm_forced_down, client):
    # A topic with nothing scheme-related must produce a usable advisory
    # (honest no-match tier), never a stuck or error flow.
    events = _run_ws(client, "I want to learn about local weather patterns.", max_steps=1)
    assert events[-1]["type"] == "done"
    advisory, _ = _advisory(events)
    assert isinstance(advisory["matched_schemes"], list)
    assert advisory["business_summary"]


def test_one_agent_failing_never_blocks_done(client):
    # Partial-research: an agent that raises mid-run must be absorbed and the
    # pipeline must still finish with a done advisory.
    from backend.agentic import nodes as agentic_nodes
    from backend.core.memory import delete_session, load_last_session

    async def _raise(_task, agent_hint=None, live_context=None):
        raise ValueError("opportunity agent crashed (test)")

    sid = "e2e_partial_research"
    original = agentic_nodes.opportunity_agent
    agentic_nodes.opportunity_agent = _raise
    try:
        events = _run_ws(client, "kirana shop expansion", max_steps=2, session_id=sid)
        assert events[-1]["type"] == "done", [e["type"] for e in events]
        # The failed node still yields a deterministic (heuristic) advisory.
        advisory, _ = _advisory(events)
        assert "business_summary" in advisory
    finally:
        agentic_nodes.opportunity_agent = original
        delete_session(sid)


def test_resume_context_flows_into_next_run(llm_forced_down, client):
    from backend.core.memory import delete_session, load_last_session

    sid = "e2e_resume_session"
    try:
        _run_ws(client, "tea stall in Delhi", max_steps=1, session_id=sid)
        # Second run with the same id advertises a resumable prior session.
        events = _run_ws(client, "tea stall in Delhi continue", max_steps=1, session_id=sid)
        assert events[-1]["type"] == "done"
        # resume context should have been advertised on the second run
        resumes = [e for e in events if e.get("type") == "resume_available"]
        assert resumes
        assert resumes[0]["previous_topic"] == "tea stall in Delhi"
    finally:
        delete_session(sid)