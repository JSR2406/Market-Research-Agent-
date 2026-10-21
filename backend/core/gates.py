"""
gates.py — human approval gates for the advisory run.

A gate is a question the agent must **not** answer on the user's behalf. S2
ships two of them, in the order the business actually faces them:

1. ``plan_approval`` — *approve the research plan before we go to the web*;
2. ``scheme_approval`` — *choose the scheme to build the plan around* — the
   moment the advisory stops being information and starts being a commitment
   (a loan, a subsidy, a repayment schedule the shopkeeper must honour).

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
GATE_KIND_SCHEME = "scheme_approval"

# ── gate statuses ────────────────────────────────────────────────────────────
GATE_PENDING = "pending"
GATE_APPROVED = "approved"
GATE_REJECTED = "rejected"

# ── the decisions a user may take ────────────────────────────────────────────
DECISION_APPROVE = "approve"
DECISION_REJECT = "reject"
VALID_DECISIONS = (DECISION_APPROVE, DECISION_REJECT)

# The choice a user makes when they do not want to take a loan right now.
SELECTION_NONE = "none"

# Caps — a gate is read on a phone screen, so it has to stay small.
MAX_GATE_STEPS = 8
MAX_GATE_SCHEMES = 6
MAX_GATE_CHOICES = 4
MAX_DECISION_NOTE = 500
MAX_GATE_ID_LEN = 64
MAX_SELECTION_LEN = 64

# Only these eligibility verdicts are worth offering as a choice: a scheme the
# user is blocked from is not a decision, it is noise.
CHOOSABLE_STATUSES = ("eligible", "likely")


def new_gate_id() -> str:
    """A short, collision-resistant id for one gate instance."""
    return f"g-{uuid.uuid4().hex[:12]}"


# ── the gate's own wording ───────────────────────────────────────────────────
# Official programme names (Udyam, MUDRA, PMEGP, CGTMSE, PM SVANidhi, GST) are
# never translated — the user must recognise them on a bank form. These strings
# deliberately contain none of them, so only the sentence around them moves.
_GATE_TEXT: Dict[str, Dict[str, Dict[str, str]]] = {
    "en": {
        GATE_KIND_PLAN: {
            "question": "Before we start, please confirm this research plan.",
            "detail": (
                "We will look up the market for your business, check the government "
                "schemes you can actually use, and then write your report."
            ),
            "approve": "Yes, go ahead",
            "reject": "No, stop here",
        },
        GATE_KIND_SCHEME: {
            "question": "Which scheme should we build your plan around?",
            "detail": (
                "These are the schemes you can use. Pick one and we will write the "
                "full steps, the papers you need and the repayment plan for it. "
                "If you would rather not take a loan right now, choose the last option."
            ),
            "approve": "Yes, use this one",
            "reject": "No, stop here",
            "none_label": "I do not want a loan right now",
            "recommended": "Best match for you",
        },
    },
    "hi": {
        GATE_KIND_PLAN: {
            "question": "शुरू करने से पहले कृपया यह रिसर्च प्लान ठीक से देख लें।",
            "detail": (
                "हम आपके कारोबार का बाज़ार देखेंगे, आपके लिए सरकारी योजनाएँ देखेंगे, "
                "और फिर आपकी रिपोर्ट लिखेंगे।"
            ),
            "approve": "हाँ, आगे बढ़ें",
            "reject": "नहीं, यहीं रोकें",
        },
        GATE_KIND_SCHEME: {
            "question": "आपका प्लान किस योजना के आधार पर बनाएँ?",
            "detail": (
                "ये वे योजनाएँ हैं जिनका आप इस्तेमाल कर सकते हैं। कोई एक चुनिए — हम "
                "उसकी पूरी प्रक्रिया, ज़रूरी काग़ज़ और किस्त का ब्योरा लिख देंगे। अगर अभी "
                "आप कर्ज़ नहीं लेना चाहते, तो आख़िरी विकल्प चुनिए।"
            ),
            "approve": "हाँ, यही चुनिए",
            "reject": "नहीं, यहीं रोकें",
            "none_label": "मुझे अभी कर्ज़ नहीं चाहिए",
            "recommended": "आपके लिए सबसे उपयुक्त",
        },
    },
}


def gate_text(lang: str, kind: str = GATE_KIND_PLAN) -> Dict[str, str]:
    """The gate wording in the requested language (English is the fallback)."""
    by_lang = _GATE_TEXT["hi" if lang == "hi" else "en"]
    return by_lang.get(kind) or by_lang[GATE_KIND_PLAN]


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
    text = gate_text(lang, GATE_KIND_PLAN)

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
        "choices": [],
        "selection": "",
        "lang": "hi" if lang == "hi" else "en",
        "max_steps": max(1, min(int(max_steps or 4), 6)),
        "created_at": time.time(),
        "decided_at": None,
        "note": "",
    }


def build_scheme_gate(
    *,
    lang: str = "en",
    families: Optional[List[Dict[str, Any]]] = None,
    max_steps: int = 4,
) -> Dict[str, Any]:
    """
    Build the scheme-commitment gate.

    ``families`` are the deterministic eligibility cards (``group_by_family``).
    Only the ones the rule engine found usable — eligible or likely — become a
    choice, because a blocked scheme is not a decision the user can make.

    The best match (the family the rule engine scored highest) is marked as the
    recommended one, so the default the user sees is the one the evidence
    points at — not the one that happened to be listed first.

    Every choice carries the official ``source_url`` and ``last_verified_at`` of
    the scheme it names. The user approves a *sourced* commitment, not a
    model-written one.
    """
    text = gate_text(lang, GATE_KIND_SCHEME)

    # Only usable families, best score first (stable: ties keep the
    # rule engine's own order).
    usable: List[Dict[str, Any]] = []
    for family in families or []:
        if not isinstance(family, dict):
            continue
        status = str(family.get("status") or "").strip().lower()
        if status not in CHOOSABLE_STATUSES:
            continue
        value = str(family.get("family") or "").strip()
        name = str(family.get("name") or "").strip()
        if not value or not name:
            continue
        try:
            score = float(family.get("score") or 0)
        except (TypeError, ValueError):
            score = 0.0
        usable.append({**family, "_value": value, "_name": name, "_score": score})
    usable.sort(key=lambda f: f["_score"], reverse=True)

    choices: List[Dict[str, Any]] = []
    for family in usable[:MAX_GATE_CHOICES]:
        recommended_id = str(family.get("recommended_scheme_id") or "")
        ceiling = ""
        for tier in family.get("tiers") or []:
            if isinstance(tier, dict) and str(tier.get("scheme_id") or "") == recommended_id:
                ceiling = str(tier.get("loan_ceiling") or "")[:80]
                break
        choices.append({
            "value": family["_value"][:MAX_SELECTION_LEN],
            "label": family["_name"][:120],
            "status": str(family.get("status_label") or family.get("status") or "")[:60],
            "loan_ceiling": ceiling,
            "source_url": str(family.get("source_url") or "")[:300],
            "last_verified_at": str(family.get("last_verified_at") or "")[:40],
            # Only the single best match is flagged — a badge on every row
            # tells the user nothing.
            "recommended": not choices,
        })

    # The "no loan" option is always last and always offered.
    choices.append({
        "value": SELECTION_NONE,
        "label": text["none_label"],
        "status": "",
        "loan_ceiling": "",
        "source_url": "",
        "last_verified_at": "",
        "recommended": False,
    })

    return {
        "gate_id": new_gate_id(),
        "kind": GATE_KIND_SCHEME,
        "status": GATE_PENDING,
        "question": text["question"],
        "detail": text["detail"],
        "options": [
            {"value": DECISION_APPROVE, "label": text["approve"]},
            {"value": DECISION_REJECT, "label": text["reject"]},
        ],
        "steps": [],
        "schemes": [],
        "choices": choices,
        "selection": "",
        "lang": "hi" if lang == "hi" else "en",
        "max_steps": max(1, min(int(max_steps or 4), 6)),
        "created_at": time.time(),
        "decided_at": None,
        "note": "",
    }


def gate_choices(gate: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The choices a gate offers (empty for a plan gate)."""
    choices = (gate or {}).get("choices")
    return [c for c in choices if isinstance(c, dict)] if isinstance(choices, list) else []


def selection_allowed(gate: Dict[str, Any], selection: str) -> bool:
    """
    Is this selection one the gate itself offered?

    The client may not invent a scheme: only the values in the gate's own
    ``choices`` are accepted, so the approval always matches what the user saw.
    """
    value = str(selection or "").strip()
    if not value:
        return False
    if value == SELECTION_NONE:
        return any(c.get("value") == SELECTION_NONE for c in gate_choices(gate))
    return any(c.get("value") == value for c in gate_choices(gate))


def scheme_choice_from_gate(
    gate: Dict[str, Any],
    selection: str,
) -> Dict[str, Any]:
    """
    The chosen scheme, as the writer must see it.

    This is what stops the report from quietly recommending a different scheme
    than the one the user approved: the writer is handed the choice — name,
    amount ceiling and official source — and told to build around it.
    """
    value = str(selection or "").strip()
    for choice in gate_choices(gate):
        if str(choice.get("value")) == value:
            return {
                "value": value,
                "name": str(choice.get("label") or ""),
                "status": str(choice.get("status") or ""),
                "loan_ceiling": str(choice.get("loan_ceiling") or ""),
                "source_url": str(choice.get("source_url") or ""),
                "last_verified_at": str(choice.get("last_verified_at") or ""),
                "recommended": bool(choice.get("recommended")),
                "is_none": value == SELECTION_NONE,
            }
    return {
        "value": value or SELECTION_NONE,
        "name": "",
        "status": "",
        "loan_ceiling": "",
        "source_url": "",
        "last_verified_at": "",
        "recommended": False,
        "is_none": True,
    }


def validate_decision(payload: Any) -> Dict[str, str]:
    """
    Validate a client-supplied gate decision.

    Raises ``ValueError`` with a short reason — the caller turns that into a
    friendly WS error. Every field is bounded, so a hostile client cannot push
    an unbounded note or a huge id into the session file. The ``selection`` is
    checked against the gate's own choices separately: only the gate knows what
    it offered.
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
    selection = str(payload.get("selection") or "").strip()
    return {
        "gate_id": gate_id,
        "decision": decision,
        "note": note[:MAX_DECISION_NOTE],
        "selection": selection[:MAX_SELECTION_LEN],
    }


def apply_decision(gate: Dict[str, Any], decision: Dict[str, str]) -> Dict[str, Any]:
    """Return a copy of ``gate`` with the user's decision applied."""
    updated = dict(gate or {})
    approved = str(decision.get("decision")) == DECISION_APPROVE
    updated["status"] = GATE_APPROVED if approved else GATE_REJECTED
    updated["decided_at"] = time.time()
    updated["note"] = str(decision.get("note") or "")[:MAX_DECISION_NOTE]
    selection = str(decision.get("selection") or "")[:MAX_SELECTION_LEN]
    if approved and selection_allowed(updated, selection):
        updated["selection"] = selection
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
        "selection": str((gate or {}).get("selection") or ""),
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
