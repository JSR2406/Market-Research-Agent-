"""
gates.py — human approval gates for the advisory run.

A gate is a question the agent must **not** answer on the user's behalf. S1
ships exactly one: *"approve the research plan before we go to the web"*.

Three rules shape this module:

1. **The gate payload is deterministic.** The question, the plan steps and the
   scheme names come from code — never from the model. The model *proposed* the
   plan; the gate *shows* the plan, but every number and every source in the
   gate is traceable to the compiled plan or to ``backend/data/schemes.json``.
2. **A gate outlives the socket.** The decision is persisted in the session
   store, so a user who closes the tab — or a server that cold-starts — can
   still approve later, and the run picks up from where it stopped.
3. **Not deciding is a normal outcome.** A timeout is not an error: the run
   parks, the gate stays pending on disk, and the user decides whenever they
   come back. Nothing is silently approved.

The broker at the bottom is the transport-neutral half: it parks a graph node
until a decision arrives on the same event loop. It holds no durable state — the
session file is the record of truth.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── gate kinds ───────────────────────────────────────────────────────────────
GATE_KIND_PLAN = "plan_approval"

# ── gate statuses ────────────────────────────────────────────────────────────
GATE_PENDING = "pending"
GATE_APPROVED = "approved"
GATE_REJECTED = "rejected"

# ── the decisions a user may take ────────────────────────────────────────────
DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
VALID_DECISIONS = (DECISION_APPROVE, DECISION_REJECT)

# Caps — a gate is read on a phone screen, so it has to stay small.
MAX_GATE_STEPS = 8
MAX_GATE_SCHEMES = 6
MAX_DECISION_NOTE = 500
MAX_GATE_ID_LEN = 64


def new_gate_id() -> str:
    """A short, collision-resistant id for one gate instance."""
    return f"g-{uuid.uuid4().hex[:12]}"


# ── the gate's own wording ───────────────────────────────────────────────────
# Official programme names (Udyam, MUDRA, PMEGP, CGTMSE, PM SVANidhi, GST) are
# never translated — the user must recognise them on a bank form. These strings
# deliberately contain none of them, so only the sentence around them moves.
_GATE_TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "question": "Before we start, please confirm this research plan.",
        "detail": (
            "We will look up the market for your business, check the government "
            "schemes you can actually use, and then write your report."
        ),
        "approve": "Yes, go ahead",
        "reject": "No, stop here",
    },
    "hi": {
        "question": "शुरू करने से पहले कृपया यह रिसर्च प्लान ठीक से देख लें।",
        "detail": (
            "हम आपके कारोबार का बाज़ार देखेंगे, आपके लिए सरकारी योजनाएँ देखेंगे, "
            "और फिर आपकी रिपोर्ट लिखेंगे।"
        ),
        "approve": "हाँ, आगे बढ़ें",
        "reject": "नहीं, यहीं रोकें",
    },
}


def gate_text(lang: str) -> Dict[str, str]:
    """The gate wording in the requested language (English is the fallback)."""
    return _GATE_TEXT["hi"] if lang == "hi" else _GATE_TEXT["en"]


def build_plan_gate(
    *,
    lang: str = "en",
    steps: Optional[List[str]] = None,
    schemes: Optional[List[Dict[str, Any]]] = None,
    max_steps: int = 4,
) -> Dict[str, Any]:
    """
    Build the plan-approval gate.

    ``steps`` are the compiled plan's steps (prose the planner proposed) and
    ``schemes`` are the deterministic eligibility families — each one already
    carries its official ``source_url`` and ``last_verified_at``. Nothing here
    is written by the model.

    ``lang`` and ``max_steps`` ride along so a run that resumes the gate later
    can be rebuilt with the same settings.
    """
    text = gate_text(lang)

    clean_steps: List[str] = []
    for step in steps or []:
        line = " ".join(str(step or "").split())
        if line:
            clean_steps.append(line[:220])
        if len(clean_steps) >= MAX_GATE_STEPS:
            break

    clean_schemes: List[Dict[str, str]] = []
    for scheme in (schemes or [])[:MAX_GATE_SCHEMES]:
        if not isinstance(scheme, dict):
            continue
        name = str(scheme.get("name") or "").strip()
        if not name:
            continue
        clean_schemes.append({
            "name": name[:120],
            "status": str(scheme.get("status_label") or scheme.get("status") or "")[:60],
            "source_url": str(scheme.get("source_url") or "")[:300],
            "last_verified_at": str(scheme.get("last_verified_at") or "")[:40],
        })

    return {
        "gate_id": new_gate_id(),
        "kind": GATE_KIND_PLAN,
        "status": GATE_PENDING,
        "question": text["question"],
        "detail": text["detail"],
        "options": [
            {"value": DECISION_APPROVE, "label": text["approve"]},
            {"value": DECISION_REJECT, "label": text["reject"]},
        ],
        "steps": clean_steps,
        "schemes": clean_schemes,
        "lang": "hi" if lang == "hi" else "en",
        "max_steps": max(1, min(int(max_steps or 4), 6)),
        "created_at": time.time(),
        "decided_at": None,
        "note": "",
    }


def validate_decision(payload: Any) -> Dict[str, str]:
    """
    Validate a client-supplied gate decision.

    Raises ``ValueError`` with a short reason — the caller turns that into a
    friendly WS error. Every field is bounded, so a hostile client cannot push
    an unbounded note or a huge id into the session file.
    """
    if not isinstance(payload, dict):
        raise ValueError("Invalid gate decision.")

    gate_id = str(payload.get("gate_id") or "").strip()
    if not gate_id or len(gate_id) > MAX_GATE_ID_LEN:
        raise ValueError("Invalid gate id.")

    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in VALID_DECISIONS:
        raise ValueError("Invalid gate decision.")

    note = str(payload.get("note") or "").strip()
    return {
        "gate_id": gate_id,
        "decision": decision,
        "note": note[:MAX_DECISION_NOTE],
    }


def apply_decision(gate: Dict[str, Any], decision: Dict[str, str]) -> Dict[str, Any]:
    """Return a copy of ``gate`` with the user's decision applied."""
    updated = dict(gate or {})
    approved = str(decision.get("decision")) == DECISION_APPROVE
    updated["status"] = GATE_APPROVED if approved else GATE_REJECTED
    updated["decided_at"] = time.time()
    updated["note"] = str(decision.get("note") or "")[:MAX_DECISION_NOTE]
    return updated


def decision_from_gate(gate: Dict[str, Any]) -> Dict[str, str]:
    """Read a decision back out of a decided gate record."""
    status = str((gate or {}).get("status") or "")
    decision = DECISION_APPROVE if status == GATE_APPROVED else (
        DECISION_REJECT if status == GATE_REJECTED else ""
    )
    return {
        "gate_id": str((gate or {}).get("gate_id") or ""),
        "decision": decision,
        "note": str((gate or {}).get("note") or ""),
    }


class GateBroker:
    """
    Bridges a parked graph run to a decision that arrives on the socket.

    One broker per WebSocket connection. The graph node parks on ``wait()``;
    the socket handler calls ``resolve()`` when the user decides. The broker
    keeps no durable state — the session file does — so a broker that dies with
    the process loses nothing but the wait.
    """

    def __init__(self) -> None:
        self._waiters: Dict[str, "asyncio.Future"] = {}

    async def wait(self, gate_id: str, timeout: float) -> Optional[Dict[str, str]]:
        """
        Park until a decision arrives or the wait times out.

        Returns the decision, or ``None`` when nobody answered in time. Never
        raises: a timeout is a normal outcome, not an error.
        """
        loop = asyncio.get_running_loop()
        future: "asyncio.Future" = loop.create_future()
        self._waiters[gate_id] = future
        try:
            return await asyncio.wait_for(future, timeout=max(1.0, float(timeout)))
        except asyncio.TimeoutError:
            logger.info("[Gates] no decision for gate %s within %ss", gate_id, timeout)
            return None
        except asyncio.CancelledError:
            raise
        finally:
            self._waiters.pop(gate_id, None)

    def resolve(self, gate_id: str, decision: Dict[str, str]) -> bool:
        """
        Hand a decision to a parked run.

        Returns False when no run is waiting on this gate — the caller then
        treats the decision as a *resume* rather than a wake-up.
        """
        future = self._waiters.get(gate_id)
        if future is None or future.done():
            return False
        future.set_result(decision)
        return True

    def pending(self) -> List[str]:
        """Ids of the gates this broker is currently waiting on."""
        return list(self._waiters.keys())

    def cancel_all(self) -> None:
        """Release every parked waiter (socket closed, run cancelled)."""
        for future in list(self._waiters.values()):
            if not future.done():
                future.cancel()
        self._waiters.clear()
