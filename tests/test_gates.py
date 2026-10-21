"""
test_gates.py — the human approval gates (S1 + S2).

The gate is the first step towards a stateful research/task agent: the run
stops, asks the user a question, and waits for an answer that is *persisted*
rather than held in a socket.

A gated run can hit more than one gate:

1. ``plan_approval`` — approve the research plan before we go to the web;
2. ``scheme_approval`` — choose the scheme the advisory is built around,
   which is the moment information turns into a commitment.

What this suite pins down:

  * the gate payload is deterministic and bounded (no model-written claims);
  * a decision is validated, capped and recorded on the session;
  * the run really stops at the gate and really continues after an approval;
  * a decline ends the run on purpose — no report, no silent approval;
  * a run that nobody answers parks on disk and can be resumed later;
  * the scheme choice is the user's, not the model's, and the report is built
    around it;
  * right-to-delete takes the gates with it.
"""
import importlib
import json

import pytest
from fastapi.testclient import TestClient

from backend.core.gates import (
    DECISION_APPROVE,
    DECISION_REJECT,
    GATE_APPROVED,
    GATE_KIND_PLAN,
    GATE_KIND_SCHEME,
    GATE_PENDING,
    GATE_REJECTED,
    SELECTION_NONE,
    apply_decision,
    build_plan_gate,
    build_scheme_gate,
    scheme_choice_from_gate,
    selection_allowed,
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
    assert ok == {"gate_id": "g-abc", "decision": "approve", "note": "ok", "selection": ""}


def test_decision_note_is_capped():
    ok = validate_decision({"gate_id": "g-abc", "decision": "approve", "note": "x" * 5000})
    assert len(ok["note"]) == 500


def test_decision_selection_is_capped():
    ok = validate_decision({"gate_id": "g-abc", "decision": "approve", "selection": "y" * 500})
    assert len(ok["selection"]) == 64


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


def _drive(ws, sid, *, selection=None, stop=("done", "error", "gate_paused"), limit=400):
    """
    Read the run to its end, answering every approval gate on the way.

    A gated run asks more than one question — approve the plan, then choose the
    scheme — so the tests drive the whole chain instead of assuming a single
    question.
    """
    seen = []
    for _ in range(limit):
        event = ws.receive_json()
        seen.append(event)
        kind = event.get("type")
        if kind == "gate_pending":
            gate = event.get("gate") or {}
            frame = {
                "type": "gate_decision",
                "session_id": sid,
                "gate_id": gate.get("gate_id"),
                "decision": "approve",
            }
            choices = gate.get("choices") or []
            if choices:
                pick = selection or choices[0].get("value")
                if pick:
                    frame["selection"] = pick
            ws.send_json(frame)
            continue
        if kind in stop:
            return event, seen
    return None, seen


def _approve_until(ws, sid, kind, limit=400):
    """Approve every gate until the gate of the wanted kind shows up."""
    for _ in range(limit):
        event = ws.receive_json()
        if event.get("type") != "gate_pending":
            continue
        gate = event.get("gate") or {}
        if gate.get("kind") == kind:
            return gate
        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": gate.get("gate_id"),
            "decision": "approve",
        })
    return None


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

        # The run then asks the second question — which scheme to build the
        # plan around — and answers it, the report comes through.
        done, seen2 = _drive(ws, sid)
        assert done is not None, seen2
        assert done["type"] == "done", seen2
        report = json.loads(done["final_report"])
        assert report["business_summary"]

    from backend.core.memory import delete_session, load_session_gates

    gates = load_session_gates(sid)
    plan = next(g for g in gates.values() if g["kind"] == GATE_KIND_PLAN)
    assert plan["status"] == GATE_APPROVED
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
        done, seen3 = _drive(ws, sid)
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


# ── the scheme gate ──────────────────────────────────────────────────────────

def test_the_gates_only_appear_in_the_trace_when_they_are_on():
    """A normal run shows no gate node at all — it has none."""
    from backend.agentic.graph import graph_topology

    off = graph_topology(False)
    off_ids = [n["id"] for n in off["nodes"]]
    assert "gate" not in off_ids
    assert "scheme_gate" not in off_ids
    assert ["supervisor", "writer"] in off["edges"]

    on = graph_topology(True)
    on_ids = [n["id"] for n in on["nodes"]]
    assert "gate" in on_ids
    assert "scheme_gate" in on_ids
    assert ["planner", "gate"] in on["edges"]
    assert ["gate", "supervisor"] in on["edges"]
    # The scheme gate takes the place of the direct supervisor → writer edge.
    assert ["supervisor", "scheme_gate"] in on["edges"]
    assert ["scheme_gate", "writer"] in on["edges"]
    assert ["supervisor", "writer"] not in on["edges"]
    # The critic's revision loop never re-asks the user.
    assert ["critic", "writer"] in on["edges"]

def _family(name, family="mudra", status="eligible", score=90, ceiling="Up to 50,000"):
    """One deterministic eligibility card, shaped like ``group_by_family``."""
    return {
        "family": family,
        "name": name,
        "status": status,
        "status_label": status.title(),
        "score": score,
        "source_url": f"https://example.gov.in/{family}",
        "last_verified_at": "2026-01-01",
        "recommended_scheme_id": f"{family}-tier",
        "tiers": [
            {
                "scheme_id": f"{family}-tier",
                "name": name,
                "status": status,
                "loan_ceiling": ceiling,
            }
        ],
    }


def test_the_scheme_gate_offers_only_schemes_the_user_can_actually_use():
    families = [
        _family("MUDRA", "mudra", "eligible", 95),
        _family("PMEGP", "pmegp", "not_eligible", 40),
        _family("PM SVANidhi", "pm-svanidhi", "blocked", 30),
        _family("CGTMSE", "cgtmse", "likely", 70),
    ]
    gate = build_scheme_gate(lang="en", families=families)
    assert gate["kind"] == GATE_KIND_SCHEME
    assert gate["status"] == GATE_PENDING

    values = [c["value"] for c in gate["choices"]]
    assert "mudra" in values
    assert "cgtmse" in values
    # A scheme the rule engine blocked is not a decision the user can make.
    assert "pmegp" not in values
    assert "pm-svanidhi" not in values
    # The "no loan" option is always there.
    assert values[-1] == SELECTION_NONE

    # Every choice carries the official source of the scheme it names.
    mudra = next(c for c in gate["choices"] if c["value"] == "mudra")
    assert mudra["source_url"] == "https://example.gov.in/mudra"
    assert mudra["last_verified_at"] == "2026-01-01"
    assert mudra["loan_ceiling"] == "Up to 50,000"

    # Exactly one choice is flagged as the best match — a badge on every row
    # would tell the user nothing.
    flagged = [c for c in gate["choices"] if c.get("recommended")]
    assert len(flagged) == 1
    assert flagged[0]["value"] == "mudra"


def test_the_scheme_gate_is_bounded():
    gate = build_scheme_gate(lang="en", families=[_family(f"S{i}", f"s{i}") for i in range(40)])
    # Four schemes plus the "no loan" option — a gate is read on a phone.
    assert len(gate["choices"]) == 5
    assert gate["choices"][-1]["value"] == SELECTION_NONE


def test_the_scheme_gate_speaks_the_users_language():
    en = build_scheme_gate(lang="en", families=[_family("MUDRA")])
    hi = build_scheme_gate(lang="hi", families=[_family("MUDRA")])
    assert en["question"] != hi["question"]
    assert hi["lang"] == "hi"
    # Official programme names are never translated — the gate text has none.
    for text in (en["question"], en["detail"], hi["question"], hi["detail"]):
        assert "MUDRA" not in text
        assert "PMEGP" not in text
        assert "Udyam" not in text


def test_the_client_cannot_invent_a_scheme():
    gate = build_scheme_gate(lang="en", families=[_family("MUDRA", "mudra")])
    assert selection_allowed(gate, "mudra") is True
    assert selection_allowed(gate, SELECTION_NONE) is True
    # A scheme the gate never offered is refused, whatever the client says.
    assert selection_allowed(gate, "pmegp") is False
    assert selection_allowed(gate, "") is False

    decided = apply_decision(
        gate, {"decision": DECISION_APPROVE, "selection": "pmegp", "note": ""}
    )
    assert decided["selection"] == ""


def test_the_chosen_scheme_is_read_back_with_its_source():
    gate = build_scheme_gate(lang="en", families=[_family("MUDRA", "mudra")])
    choice = scheme_choice_from_gate(gate, "mudra")
    assert choice["value"] == "mudra"
    assert choice["name"] == "MUDRA"
    assert choice["source_url"] == "https://example.gov.in/mudra"
    assert choice["is_none"] is False

    no_loan = scheme_choice_from_gate(gate, SELECTION_NONE)
    assert no_loan["is_none"] is True


def test_the_scheme_gate_is_skipped_when_there_is_nothing_to_choose():
    """No usable scheme → no question. A gate with only "no loan" is noise."""
    import asyncio

    from backend.agentic.nodes import scheme_gate_node

    class _Emitter:
        is_cancelled = False

        def __init__(self):
            self.events = []

        async def node_start(self, node, label, **kw):
            self.events.append(("start", node))
            return 0

        async def node_end(self, node, label, idx, **kw):
            self.events.append(("end", node))

        async def thought(self, node, text):
            self.events.append(("thought", node))

        async def gate_pending(self, gate):
            self.events.append(("gate_pending", gate))

        async def gate_decided(self, gate):
            self.events.append(("gate_decided", gate))

    emitter = _Emitter()
    config = {"configurable": {"emitter": emitter, "session_id": "", "gate_broker": None}}
    state = {"eligibility_families": [], "output_lang": "en"}

    out = asyncio.run(scheme_gate_node(state, config))
    kinds = [e[0] for e in emitter.events]
    assert "gate_pending" not in kinds
    assert out.get("scheme_choice", {}) == {}


def test_every_gate_the_session_saw_is_stored(tmp_path, monkeypatch):
    """Two gates, two records — the run remembers both decisions."""
    from backend.core import memory

    monkeypatch.setattr(memory, "SESSIONS_DIR", tmp_path)
    sid = "gate_two_session"

    plan = build_plan_gate()
    memory.save_session_gate(sid, plan, topic="kirana shop")
    memory.record_gate_decision(
        sid, {"gate_id": plan["gate_id"], "decision": DECISION_APPROVE, "note": ""}
    )

    scheme = build_scheme_gate(lang="en", families=[_family("MUDRA", "mudra")])
    memory.save_session_gate(sid, scheme, topic="kirana shop")

    gates = memory.load_session_gates(sid)
    assert set(gates) == {plan["gate_id"], scheme["gate_id"]}
    assert gates[plan["gate_id"]]["status"] == GATE_APPROVED
    assert gates[scheme["gate_id"]]["status"] == GATE_PENDING
    # The one the user has to act on is the most recent.
    assert memory.load_session_gate(sid)["gate_id"] == scheme["gate_id"]

    decisions = memory.load_session_gate_decisions(sid)
    assert decisions[GATE_KIND_PLAN]["decision"] == DECISION_APPROVE
    # A pending gate has no decision yet.
    assert GATE_KIND_SCHEME not in decisions


def test_choosing_a_scheme_shapes_the_report(client):
    """The user's choice — not the model's — decides what the report is about."""
    sid = "gate_ws_scheme"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
            "gates": True,
        })

        scheme_gate = _approve_until(ws, sid, GATE_KIND_SCHEME)
        assert scheme_gate is not None
        choices = scheme_gate["choices"]
        assert choices, scheme_gate
        pick = choices[0]

        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": scheme_gate["gate_id"],
            "decision": "approve",
            "selection": pick["value"],
        })

        done, seen = _drive(ws, sid)
        assert done is not None, seen
        assert done["type"] == "done", seen

        report = json.loads(done["final_report"])
        # The choice is in the report itself, not only in the session file.
        assert report["scheme_choice"]["value"] == pick["value"]
        assert report["scheme_choice"]["name"] == pick["label"]
        # And it leads the schemes the report talks about — a commitment the
        # user made outranks a recommendation the model made.
        matched = report.get("matched_schemes") or []
        assert matched, report
        assert pick["label"].lower() in matched[0].lower()

    from backend.core.memory import delete_session, load_session_gates

    gates = load_session_gates(sid)
    scheme = next(g for g in gates.values() if g["kind"] == GATE_KIND_SCHEME)
    assert scheme["status"] == GATE_APPROVED
    assert scheme["selection"] == pick["value"]
    delete_session(sid)


def test_declining_the_scheme_gate_ends_the_run(client):
    """Saying no to the commitment is as final as saying no to the plan."""
    sid = "gate_ws_scheme_reject"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
            "gates": True,
        })

        scheme_gate = _approve_until(ws, sid, GATE_KIND_SCHEME)
        assert scheme_gate is not None

        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": scheme_gate["gate_id"],
            "decision": "reject",
        })

        paused, seen = _read_until(ws, {"gate_paused", "done", "error"})
        assert paused is not None, seen
        assert paused["type"] == "gate_paused", seen
        assert paused["status"] == GATE_REJECTED
        assert "done" not in [e.get("type") for e in seen]

    from backend.core.memory import delete_session, load_session_gates

    gates = load_session_gates(sid)
    scheme = next(g for g in gates.values() if g["kind"] == GATE_KIND_SCHEME)
    assert scheme["status"] == GATE_REJECTED
    delete_session(sid)


def test_an_invented_scheme_is_refused(client):
    """The gate is the authority on what may be chosen."""
    sid = "gate_ws_scheme_junk"
    with client.websocket_connect("/ws/market") as ws:
        ws.send_json({
            "type": "start",
            "topic": "I run a small kirana shop and want to buy new stock.",
            "max_steps": 2,
            "session_id": sid,
            "gates": True,
        })

        scheme_gate = _approve_until(ws, sid, GATE_KIND_SCHEME)
        assert scheme_gate is not None

        ws.send_json({
            "type": "gate_decision",
            "session_id": sid,
            "gate_id": scheme_gate["gate_id"],
            "decision": "approve",
            "selection": "a-scheme-that-does-not-exist",
        })

        event = ws.receive_json()
        assert event["type"] == "error"
        assert "choose one of the options" in event["message"].lower()

    from backend.core.memory import delete_session, load_session_gates

    gates = load_session_gates(sid)
    scheme = next(g for g in gates.values() if g["kind"] == GATE_KIND_SCHEME)
    # Nothing was approved, so nothing was chosen.
    assert scheme["status"] == GATE_PENDING
    assert scheme["selection"] == ""
    delete_session(sid)
