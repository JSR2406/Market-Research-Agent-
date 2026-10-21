"""
memory.py — the local, JSON-backed session store (research history + chat).

Two things are persisted per browser session id, in two sibling files:

  {session_id}.json       the research session: its runs and the facts we
                          learned about the business
  {session_id}_chat.json  the advisor-chat history

Why the shape looks like this
-----------------------------
A session used to hold exactly one advisory: every new run overwrote the last,
so the user could not look back at what they had done. This module keeps a
**history** instead — the newest run sits at ``runs[0]`` (capped at
``MAX_RUNS_PER_SESSION``) — while still exposing the latest run's state under a
top-level ``state`` key. That top-level mirror is deliberate: every legacy
reader (the ledger, the chat context, WhatsApp, resume) keeps working unchanged,
so the history layer is additive rather than a breaking rewrite.

Derived **facts** (business type, location, last eligible amount, last
loan-ready score, ...) are recomputed from each run and merged forward, so the
advisor chat can remember the business across separate conversations without
ever re-reading a whole report.

Data-accuracy / privacy notes:
  * Facts are copied verbatim from user answers or from deterministic outputs —
    never invented, never LLM-written.
  * Session ids are client-controlled and used as file names, so they are
    restricted to a strict allowlist (see ``is_valid_session_id``).
  * Sessions older than 7 days are removed on startup (``cleanup_old_sessions``);
    ``delete_session`` is the user-triggered, GDPR right-to-delete purge and
    removes the chat file too.
"""
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
SESSIONS_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions"))

# Chat history cap per session (safe window for the LLM context, bounded storage)
MAX_CHAT_MESSAGES = 40

# How many past research runs a session keeps. Enough to compare "before and
# after" without letting a single session grow without bound. The history UI
# reads every one of these (newest first), so this is the size of the stored
# session history.
MAX_RUNS_PER_SESSION = 50

# Session ids are client-controlled and are used to build file paths — they are
# therefore restricted to a strict allowlist (frontend generates `s-<ts>-<rand>`,
# WhatsApp uses `wa-<number>`). Anything else would enable path traversal
# (e.g. `../../data/schemes` resolving outside SESSIONS_DIR).
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_valid_session_id(session_id) -> bool:
    """True when the id is a safe, path-free session identifier."""
    return isinstance(session_id, str) and bool(_SESSION_ID_RE.match(session_id))


def _require_valid_session_id(session_id: str, *, allow_empty: bool = False) -> str:
    if allow_empty and not session_id:
        return session_id
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid session id.")
    return session_id


def _init_dir() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _chat_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}_chat.json"


# ─────────────────────────────────────────────────────────────────────────────
# Structure helpers
# ─────────────────────────────────────────────────────────────────────────────

def _empty_session(session_id: str = "") -> Dict[str, Any]:
    now = time.time()
    return {
        "session_id": session_id,
        "topic": "",
        "state": {},
        "runs": [],
        "facts": {},
        "intake": {},
        "gate": {},
        "gates": {},
        "created_at": now,
        "updated_at": now,
    }


def _run_from_state(topic: str, state: Dict[str, Any], *, run_id: Optional[str] = None,
                    created_at: Optional[float] = None) -> Dict[str, Any]:
    """Build one history entry from an executor state dict.

    The full ``state`` is kept under ``state`` (so nothing is lost), and the
    fields the UI/chat care about are mirrored at the top level for cheap access.
    """
    state = state if isinstance(state, dict) else {}
    return {
        "run_id": run_id or str(uuid.uuid4())[:8],
        "created_at": created_at if created_at is not None else time.time(),
        "topic": topic or "",
        "final_report": state.get("final_report", ""),
        "simplified_report": state.get("simplified_report", ""),
        "eligibility": state.get("eligibility", {}) or {},
        "ledger": state.get("ledger", {}) or {},
        "plan": state.get("plan", []) or [],
        "plan_run": state.get("plan_run", {}) or {},
        "intake": state.get("intake", {}) or {},
        "profile": state.get("profile", "") or "",
        "sources": state.get("sources", []) or [],
        "token_usage": state.get("token_usage", {}) or {},
        "engine": state.get("engine", "") or "",
        # Full state last, so a legacy reader that only knows `state` still works.
        "state": state,
    }


def _migrate_old_session(session_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Upgrade a pre-history ``{topic, state, updated_at}`` file in place."""
    old_state = data.get("state") if isinstance(data.get("state"), dict) else {}
    session = _empty_session(session_id)
    session["created_at"] = data.get("updated_at", time.time())
    session["updated_at"] = data.get("updated_at", time.time())
    session["topic"] = data.get("topic", "")
    session["state"] = old_state
    if old_state:
        run = _run_from_state(
            data.get("topic", ""), old_state,
            created_at=data.get("updated_at", time.time()),
        )
        session["runs"] = [run]
        session["facts"] = _extract_facts(run)
    session["intake"] = old_state.get("intake", {}) or {}
    return session


def _normalize_session(session_id: str, data: Any) -> Dict[str, Any]:
    """Return a well-formed session dict, migrating or resetting as needed."""
    if not isinstance(data, dict):
        if data is not None:
            logger.warning("Session %s data is not a dict (%s) — starting fresh.", session_id, type(data).__name__)
        session = _empty_session(session_id)
        session["session_id"] = session_id
        return session

    # Old single-run format: has `state` but no `runs` list.
    if "runs" not in data and "state" in data:
        return _migrate_old_session(session_id, data)

    session = _empty_session(session_id)
    session.update({k: v for k, v in data.items() if k in session})
    session["session_id"] = session_id
    if not isinstance(session.get("runs"), list):
        session["runs"] = []
    if not isinstance(session.get("facts"), dict):
        session["facts"] = {}
    if not isinstance(session.get("intake"), dict):
        session["intake"] = {}
    if not isinstance(session.get("gate"), dict):
        session["gate"] = {}
    if not isinstance(session.get("gates"), dict):
        session["gates"] = {}
    if not isinstance(session.get("state"), dict):
        session["state"] = {}
    session.setdefault("topic", "")
    session.setdefault("created_at", time.time())
    session.setdefault("updated_at", time.time())
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Facts — the cross-session memory the advisor chat reads
# ─────────────────────────────────────────────────────────────────────────────

# Human-readable fact keys for the intake field ids (kept explicit so the chat
# context reads naturally instead of echoing internal ids like `loan`).
_INTAKE_FACT_KEYS = {
    "business": "business_type",
    "offering": "offering",
    "scale": "business_scale",
    "age": "business_age",
    "earnings": "monthly_earnings",
    "location": "location",
    "loan": "loan_history",
    "need": "main_need",
    "registered": "registration",
}


def _extract_facts(run: Dict[str, Any]) -> Dict[str, Any]:
    """Derive cross-session facts from one run. Deterministic and copy-only."""
    facts: Dict[str, Any] = {}

    intake = run.get("intake") or {}
    if isinstance(intake, dict):
        for field_id, fact_key in _INTAKE_FACT_KEYS.items():
            value = intake.get(field_id)
            if isinstance(value, str) and value.strip():
                facts[fact_key] = value.strip()

    eligibility = run.get("eligibility") or {}
    if isinstance(eligibility, dict):
        if eligibility.get("business_class"):
            facts["last_business_class"] = eligibility["business_class"]
        if eligibility.get("amount"):
            facts["last_eligible_amount"] = eligibility["amount"]

    ledger = run.get("ledger") or {}
    if isinstance(ledger, dict) and ledger.get("score") is not None:
        facts["last_loan_ready_score"] = ledger["score"]

    # `plan` is a list of step strings in the run state (older builds and the
    # agentic planner both emit a list); tolerate a dict too.
    plan = run.get("plan")
    if isinstance(plan, dict) and plan.get("goal"):
        facts["last_research_goal"] = plan["goal"]
    elif isinstance(plan, list) and plan:
        facts["last_research_goal"] = str(plan[0])[:200]

    if run.get("topic"):
        facts["last_topic"] = str(run["topic"])[:200]

    facts["updated_at"] = time.time()
    return facts


def _merge_facts(existing: Dict[str, Any], new_facts: Dict[str, Any]) -> Dict[str, Any]:
    """Merge new facts over the old, ignoring empty values."""
    merged = dict(existing) if isinstance(existing, dict) else {}
    for key, value in new_facts.items():
        if value not in (None, "", [], {}):
            merged[key] = value
    merged["updated_at"] = time.time()
    return merged


# ─────────────────────────────────────────────────────────────────────────────
# Read / write
# ─────────────────────────────────────────────────────────────────────────────

def _read_raw(session_id: str) -> Dict[str, Any]:
    path = _session_file(session_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to read session %s: %s", session_id, e)
        return {}


def _write(session_id: str, session: Dict[str, Any]) -> None:
    session["updated_at"] = time.time()
    try:
        _session_file(session_id).write_text(
            json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.error("Failed to save session %s: %s", session_id, e)


def save_session(session_id: str, topic: str, state: dict) -> None:
    """
    Persist one research run: append it to ``runs[]`` (newest first, capped),
    mirror the latest state at the top level, and merge its facts forward.
    """
    _require_valid_session_id(session_id)
    _init_dir()

    session = _normalize_session(session_id, _read_raw(session_id))
    state = state if isinstance(state, dict) else {}

    run = _run_from_state(topic, state)
    session["runs"].insert(0, run)
    session["runs"] = session["runs"][:MAX_RUNS_PER_SESSION]

    # Latest-state mirror — every legacy reader depends on this.
    session["state"] = state
    session["topic"] = topic or session.get("topic", "")

    session["facts"] = _merge_facts(session.get("facts", {}), _extract_facts(run))

    intake = state.get("intake")
    if isinstance(intake, dict) and intake:
        session["intake"] = intake

    _write(session_id, session)


def update_session_state(session_id: str, patch: dict) -> None:
    """
    Merge ``patch`` into the newest run's state **without** appending a new run.

    Used by the Action Ledger when the user ticks progress: the score moves, but
    the run history should not gain a phantom entry.
    """
    _require_valid_session_id(session_id)
    if not isinstance(patch, dict) or not patch:
        return
    _init_dir()

    session = _normalize_session(session_id, _read_raw(session_id))
    state = session.get("state")
    if not isinstance(state, dict):
        state = {}
    state.update(patch)
    session["state"] = state

    if session.get("runs"):
        run = session["runs"][0]
        run["state"] = state
        for key in ("final_report", "simplified_report", "eligibility", "ledger",
                    "plan", "plan_run", "intake", "profile", "sources",
                    "token_usage", "engine"):
            if key in state:
                run[key] = state[key]
        session["facts"] = _merge_facts(session.get("facts", {}), _extract_facts(run))

    _write(session_id, session)


# ─────────────────────────────────────────────────────────────────────────────
# Approval gates
# ─────────────────────────────────────────────────────────────────────────────
# A parked run has not produced a report yet, so it must NOT appear in the run
# history — but the gate itself has to outlive the socket, so it lives on the
# session record next to the topic and the intake it belongs to. That makes a
# gate resumable: the user can approve it tomorrow and the run picks up from
# the same Business Check-up answers.
#
# A gated run can hit more than one gate (approve the plan, then choose the
# scheme), so every gate the session has seen is kept in ``session["gates"]``
# keyed by its id. ``session["gate"]`` stays as the one the user has to act on
# — the most recent — so the UI contract does not change.


def _latest_gate(gates: Dict[str, Any]) -> Dict[str, Any]:
    """The gate the user has to act on: the most recent one."""
    best: Dict[str, Any] = {}
    best_at = -1.0
    for gate in (gates or {}).values():
        if not isinstance(gate, dict):
            continue
        try:
            at = float(gate.get("created_at") or 0)
        except (TypeError, ValueError):
            at = 0.0
        if at >= best_at:
            best_at = at
            best = gate
    return best


def _store_gate(session: Dict[str, Any], gate: Dict[str, Any]) -> None:
    """Put a gate into the session's gate map and refresh the pending pointer."""
    gates = session.get("gates")
    if not isinstance(gates, dict):
        gates = {}
    gate_id = str((gate or {}).get("gate_id") or "")
    if gate_id:
        gates[gate_id] = gate
    session["gates"] = gates
    session["gate"] = _latest_gate(gates)


def save_session_gate(
    session_id: str,
    gate: Dict[str, Any],
    *,
    topic: str = "",
    intake: Optional[Dict[str, str]] = None,
) -> None:
    """Persist a pending or decided gate without appending a run."""
    _require_valid_session_id(session_id)
    if not isinstance(gate, dict) or not gate:
        return
    _init_dir()

    session = _normalize_session(session_id, _read_raw(session_id))
    _store_gate(session, gate)
    if topic:
        session["topic"] = topic
    if isinstance(intake, dict) and intake:
        session["intake"] = intake
    _write(session_id, session)


def load_session_gate(session_id: str) -> Dict[str, Any]:
    """The gate the user has to act on (empty when there is none)."""
    if not is_valid_session_id(session_id):
        return {}
    gate = (load_last_session(session_id) or {}).get("gate")
    return gate if isinstance(gate, dict) else {}


def load_session_gates(session_id: str) -> Dict[str, Dict[str, Any]]:
    """Every gate this session has seen, keyed by gate id."""
    if not is_valid_session_id(session_id):
        return {}
    gates = (load_last_session(session_id) or {}).get("gates")
    if not isinstance(gates, dict):
        return {}
    return {k: v for k, v in gates.items() if isinstance(v, dict)}


def load_session_gate_by_id(session_id: str, gate_id: str) -> Dict[str, Any]:
    """One gate by id (empty when the session has no such gate)."""
    return load_session_gates(session_id).get(str(gate_id or ""), {})


def load_session_gate_decisions(session_id: str) -> Dict[str, Dict[str, str]]:
    """
    The decisions already taken on this session's gates, keyed by gate kind.

    A resumed run needs every decision it already earned: approving the plan
    must not be asked again just because the run stopped later, at the scheme
    gate.
    """
    from backend.core.gates import decision_from_gate

    decisions: Dict[str, Dict[str, str]] = {}
    for gate in load_session_gates(session_id).values():
        kind = str(gate.get("kind") or "")
        if not kind:
            continue
        decision = decision_from_gate(gate)
        if decision.get("decision"):
            decisions[kind] = decision
    return decisions


def record_gate_decision(session_id: str, decision: Dict[str, str]) -> Dict[str, Any]:
    """
    Apply a decision to the stored gate and persist it.

    Returns the updated gate record. A decision for an unknown gate — or for a
    gate that has already been decided — is a no-op: the user gets a friendly
    answer and nothing is written.
    """
    _require_valid_session_id(session_id)
    gate = load_session_gate_by_id(session_id, str(decision.get("gate_id") or ""))
    if not gate:
        return {}
    if str(gate.get("status")) != "pending":
        return {}

    from backend.core.gates import apply_decision

    updated = apply_decision(gate, decision)
    _init_dir()
    session = _normalize_session(session_id, _read_raw(session_id))
    _store_gate(session, updated)
    _write(session_id, session)
    return updated


def clear_session_gate(session_id: str) -> None:
    """
    Drop the stored gates for a session.

    A fresh run means fresh gates: leaving the old ones behind would let a
    stale approval resume a run the user has already replaced.
    """
    _require_valid_session_id(session_id)
    if not _session_file(session_id).exists():
        return
    session = _normalize_session(session_id, _read_raw(session_id))
    if not session.get("gate") and not session.get("gates"):
        return
    session["gate"] = {}
    session["gates"] = {}
    _write(session_id, session)


def load_last_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Load the full session (runs + facts + intake + latest state)."""
    if not is_valid_session_id(session_id):
        return None
    if not _session_file(session_id).exists():
        return None
    return _normalize_session(session_id, _read_raw(session_id))

def load_session_state(session_id: str) -> Dict[str, Any]:
    """Return the latest run's state dict (empty when nothing is stored)."""
    return (load_last_session(session_id) or {}).get("state") or {}


def load_latest_run(session_id: str) -> Optional[Dict[str, Any]]:
    """Return the newest run in the legacy ``{topic, state, updated_at}`` shape."""
    session = load_last_session(session_id)
    if not session or not session.get("runs"):
        return None
    run = session["runs"][0]
    return {
        "session_id": session_id,
        "topic": run.get("topic", ""),
        "state": run.get("state", {}),
        "updated_at": run.get("created_at"),
    }


def get_runs_list(session_id: str) -> List[Dict[str, Any]]:
    """Lightweight run summaries for the history UI (no full reports)."""
    session = load_last_session(session_id)
    if not session:
        return []
    runs = []
    for run in session.get("runs", []):
        ledger = run.get("ledger") or {}
        eligibility = run.get("eligibility") or {}
        runs.append({
            "run_id": run.get("run_id"),
            "created_at": run.get("created_at"),
            "topic": (run.get("topic") or "")[:120],
            "has_report": bool(run.get("final_report")),
            "eligibility": {
                "business_class": eligibility.get("business_class", ""),
                "business_label": eligibility.get("business_label", ""),
                "amount": eligibility.get("amount"),
            },
            "loan_ready_score": ledger.get("score"),
        })
    return runs


def load_run(session_id: str, run_id: str) -> Optional[Dict[str, Any]]:
    """Load one historical run (legacy ``{topic, state, updated_at}`` shape)."""
    session = load_last_session(session_id)
    if not session:
        return None
    for run in session.get("runs", []):
        if run.get("run_id") == run_id:
            return {
                "session_id": session_id,
                "run_id": run_id,
                "topic": run.get("topic", ""),
                "state": run.get("state", {}),
                "updated_at": run.get("created_at"),
            }
    return None


def get_session_facts(session_id: str) -> Dict[str, Any]:
    """Cross-session facts for advisor context."""
    return (load_last_session(session_id) or {}).get("facts", {}) or {}


def get_session_intake(session_id: str) -> Dict[str, Any]:
    """The latest persisted Business Check-up answers for a session."""
    return (load_last_session(session_id) or {}).get("intake", {}) or {}


def build_resume_context(prior_data: dict) -> str:
    """Build a short continuity string from the most recent run."""
    if not isinstance(prior_data, dict):
        return ""
    runs = prior_data.get("runs")
    if isinstance(runs, list) and runs:
        topic = runs[0].get("topic", "")
        final_report = runs[0].get("final_report", "")
    else:
        topic = prior_data.get("topic", "")
        final_report = (prior_data.get("state") or {}).get("final_report", "")

    business_summary = ""
    try:
        if final_report:
            clean_json = final_report.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean_json)
            business_summary = parsed.get("business_summary", "")
    except Exception:
        business_summary = str(final_report)[:200]

    if not topic and not business_summary:
        return ""
    return f"Previous business context: {topic}. Summary: {business_summary}"


def delete_session(session_id: str) -> None:
    """GDPR right-to-delete: drop the session file, chat memory and tracker."""
    _require_valid_session_id(session_id)
    path = _session_file(session_id)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass
    clear_chat(session_id)
    # The application tracker (WS-6) is another sibling file held under the same
    # session id, so right-to-delete has to take it with it.
    tracker_path = SESSIONS_DIR / f"{session_id}_tracker.json"
    if tracker_path.exists():
        try:
            tracker_path.unlink()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Chat memory (per-session conversation history)
# ─────────────────────────────────────────────────────────────────────────────

def save_chat_message(session_id: str, role: str, content: str) -> None:
    """Append one chat message (cap at MAX_CHAT_MESSAGES, drop oldest)."""
    _require_valid_session_id(session_id)
    _init_dir()
    data: Dict[str, Any] = {"session_id": session_id, "messages": [], "updated_at": time.time()}
    path = _chat_path(session_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    if not isinstance(data, dict):
        data = {"session_id": session_id, "messages": []}
    data.setdefault("messages", []).append(
        {"role": role, "content": str(content), "ts": time.time()}
    )
    data["messages"] = data["messages"][-MAX_CHAT_MESSAGES:]
    data["updated_at"] = time.time()
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error("Failed to save chat for session %s: %s", session_id, e)


def load_chat_history(session_id: str, limit: int = 20) -> list:
    """Return the most recent chat messages as [{"role", "content"}, ...]."""
    if not session_id or not is_valid_session_id(session_id):
        return []
    path = _chat_path(session_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            {"role": m.get("role", "user"), "content": m.get("content", "")}
            for m in data.get("messages", [])
        ][-limit:]
    except Exception as e:
        logger.error("Failed to load chat for session %s: %s", session_id, e)
        return []


def clear_chat(session_id: str) -> None:
    _require_valid_session_id(session_id)
    path = _chat_path(session_id)
    if path.exists():
        try:
            path.unlink()
        except Exception:
            pass


def cleanup_old_sessions() -> int:
    """Delete sessions (and their chat files) older than 7 days."""
    _init_dir()
    deleted = 0
    now = time.time()
    try:
        for f in SESSIONS_DIR.glob("*.json"):
            if f.is_file():
                try:
                    if now - f.stat().st_mtime > 7 * 24 * 60 * 60:
                        f.unlink()
                        deleted += 1
                except Exception:
                    continue
    except Exception:
        pass
    return deleted
