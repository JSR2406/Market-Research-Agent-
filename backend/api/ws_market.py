"""
ws_market.py — WebSocket endpoint for the market research workflow.

Messages handled:
- `start`: begin a run (optionally resume a prior session via session_id)
- `gate_decision`: approve or decline a run that is waiting at an approval gate
- `cancel`: cancel the running workflow
- `delete_session`: GDPR right-to-delete
- `export_session`: export stored session data

Hardening notes (P0):
- All client input is type-checked and size-capped before use.
- `session_id` is validated against the strict allowlist in core.memory
  (path-traversal guard) before it touches disk.
- Client-facing errors are generic; details go to server logs only.
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.config import ALLOWED_ORIGINS, GATES_ENABLED
from backend.core.gates import (
    DECISION_APPROVE,
    DECISION_REJECT,
    GATE_KIND_PLAN,
    GATE_KIND_SCHEME,
    GATE_REJECTED,
    GateBroker,
    selection_allowed,
    validate_decision,
)
from backend.core.intake import normalize_intake
from backend.core.memory import (
    build_resume_context,
    clear_session_gate,
    delete_session,
    is_valid_session_id,
    load_last_session,
    load_session_gate_by_id,
    load_session_gate_decisions,
    load_session_gates,
    record_gate_decision,
)
from backend.core.ws import SafeWebSocket
from backend.workflows.executor import run_research_workflow

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_TOPIC_CHARS = 4000
MAX_PROFILE_CHARS = 1500
VALID_LANGS = ("en", "hi")


def _as_lang(value) -> str:
    """Client-declared output language; anything else falls back to English."""
    return value.strip().lower() if isinstance(value, str) and value.strip().lower() in VALID_LANGS else "en"


def _as_bool(value) -> bool:
    """A client-supplied on/off flag. Only an explicit true counts."""
    return value is True or (isinstance(value, str) and value.strip().lower() in ("1", "true", "yes"))


def _origin_allowed(websocket: WebSocket) -> bool:
    """
    Cross-site WebSocket hijacking guard. Browsers always send an Origin
    header on a WS handshake; a page on another domain must not be able to
    open this socket and drive the research pipeline.

    - No Origin (curl, server-to-server, test clients) → allowed.
    - Origin matching the request's own host (scheme://host[:port]) → allowed.
    - Otherwise the origin must be listed in ALLOWED_ORIGINS.
    """
    origin = (websocket.headers.get("origin") or "").strip().rstrip("/")
    if not origin:
        return True
    if origin in ALLOWED_ORIGINS:
        return True
    host = (websocket.headers.get("host") or "").strip()
    if host and origin in (f"http://{host}", f"https://{host}"):
        return True
    return False


def _as_str(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _as_intake(value) -> dict:
    """Structured Business Check-up answers — normalized before any agent sees them."""
    return normalize_intake(value if isinstance(value, dict) else None)


def _safe_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.websocket("/ws/market")
async def market_research_websocket(websocket: WebSocket):
    # Reject foreign browser origins BEFORE accepting the socket.
    if not _origin_allowed(websocket):
        logger.warning(
            "Rejected WS connection from disallowed origin: %s",
            websocket.headers.get("origin"),
        )
        await websocket.close(code=1008)
        return

    await websocket.accept()
    ws = SafeWebSocket(websocket)

    cancel_flag = {"cancelled": False}
    workflow_task = None
    # One broker per connection: it parks a run at its approval gate and wakes
    # it when the user's decision arrives on this socket.
    broker = GateBroker()

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                await ws.send_json({
                    "type": "error",
                    "message": "That message could not be read. Please refresh and try again.",
                })
                continue

            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "message": "Unsupported message."})
                continue

            msg_type = msg.get("type")

            if msg_type == "start":
                topic = _as_str(msg.get("topic"))[:MAX_TOPIC_CHARS]
                profile = _as_str(msg.get("profile"))[:MAX_PROFILE_CHARS]
                intake = _as_intake(msg.get("intake"))
                lang = _as_lang(msg.get("lang"))
                session_id = _as_str(msg.get("session_id"))
                max_steps = max(1, min(_safe_int(msg.get("max_steps", 4), 4), 6))
                # The approval gate is off unless this run asks for it (or the
                # deployment turned it on for every run).
                gates_enabled = bool(GATES_ENABLED) or _as_bool(msg.get("gates"))

                if not topic:
                    await ws.send_json({"type": "error", "message": "Topic is empty."})
                    continue

                if session_id and not is_valid_session_id(session_id):
                    await ws.send_json({"type": "error", "message": "Invalid session id."})
                    continue

                cancel_flag["cancelled"] = False

                # Load prior session context for continuity.
                session_context = ""
                if session_id:
                    try:
                        prior = load_last_session(session_id)
                        if prior:
                            session_context = build_resume_context(prior)
                            # New format: topic is in runs[0]["topic"]
                            previous_topic = ""
                            runs = prior.get("runs", [])
                            if runs:
                                previous_topic = runs[0].get("topic", "")
                            elif prior.get("topic"):
                                # Fallback: old format
                                previous_topic = prior.get("topic", "")
                            await ws.send_json({
                                "type": "resume_available",
                                "session_id": session_id,
                                "previous_topic": previous_topic,
                                "summary": session_context[:300],
                            })
                    except Exception:
                        logger.warning("Failed to load resume context", exc_info=True)
                        # never block a run because of memory errors

                # Cancel the previous task if still running.
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                broker.cancel_all()

                # A fresh run means a fresh gate — a stale approval must not be
                # able to resume a run the user has already replaced.
                if session_id:
                    try:
                        clear_session_gate(session_id)
                    except Exception:
                        logger.warning("Could not clear the previous gate", exc_info=True)

                workflow_task = asyncio.create_task(
                    run_research_workflow(
                        topic, max_steps, ws, cancel_flag,
                        session_context=session_context,
                        session_id=session_id,
                        profile=profile,
                        intake=intake,
                        lang=lang,
                        gates_enabled=gates_enabled,
                        gate_broker=broker,
                    )
                )

            elif msg_type == "gate_decision":
                session_id = _as_str(msg.get("session_id"))
                if not is_valid_session_id(session_id):
                    await ws.send_json({"type": "error", "message": "Invalid session id."})
                    continue
                try:
                    decision = validate_decision(msg)
                except ValueError:
                    await ws.send_json({
                        "type": "error",
                        "message": "That decision could not be read. Please try again.",
                    })
                    continue

                # The gate itself is the authority on what may be chosen: the
                # client may only pick a value the gate offered.
                pending_gate = load_session_gate_by_id(session_id, decision["gate_id"])
                if not pending_gate:
                    await ws.send_json({
                        "type": "error",
                        "message": "This approval is no longer waiting. Please start the research again.",
                    })
                    continue
                if (
                    str(pending_gate.get("kind")) == GATE_KIND_SCHEME
                    and decision["decision"] == DECISION_APPROVE
                    and not selection_allowed(pending_gate, decision.get("selection", ""))
                ):
                    await ws.send_json({
                        "type": "error",
                        "message": "Please choose one of the options before you approve.",
                    })
                    continue

                # Record it on disk first — the decision has to survive the
                # socket even when the run that was waiting for it is gone.
                stored = record_gate_decision(session_id, decision)
                if not stored:
                    await ws.send_json({
                        "type": "error",
                        "message": "This approval is no longer waiting. Please start the research again.",
                    })
                    continue

                # Wake the run that is parked on this gate.
                if broker.resolve(decision["gate_id"], decision):
                    await ws.send_json({"type": "gate_decided", "gate": stored})
                    continue

                # A decline ends the run on purpose — there is nothing to resume.
                if decision["decision"] == DECISION_REJECT:
                    await ws.send_json({
                        "type": "gate_paused",
                        "gate": stored,
                        "status": GATE_REJECTED,
                    })
                    continue

                # Nothing was waiting: the run had already parked (the tab was
                # closed, or the wait timed out). Resume it from the persisted
                # topic and Business Check-up answers with the decision applied.
                prior = load_last_session(session_id) or {}
                resume_topic = str(prior.get("topic") or "")[:MAX_TOPIC_CHARS]
                resume_intake = _as_intake(prior.get("intake"))
                if not resume_topic:
                    await ws.send_json({
                        "type": "error",
                        "message": "We could not find the paused research. Please start it again.",
                    })
                    continue

                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                cancel_flag["cancelled"] = False

                # A run can hit more than one gate, so the resume carries every
                # decision it already earned: approving the plan must not be
                # asked again just because the run stopped later, at the scheme
                # gate.
                decisions = load_session_gate_decisions(session_id)
                gates = load_session_gates(session_id)
                plan_gate = next(
                    (g for g in gates.values() if str(g.get("kind")) == GATE_KIND_PLAN), {},
                )
                scheme_gate = next(
                    (g for g in gates.values() if str(g.get("kind")) == GATE_KIND_SCHEME), {},
                )

                workflow_task = asyncio.create_task(
                    run_research_workflow(
                        resume_topic,
                        max(1, min(_safe_int(stored.get("max_steps"), 4), 6)),
                        ws,
                        cancel_flag,
                        session_id=session_id,
                        intake=resume_intake,
                        lang=_as_lang(stored.get("lang")),
                        gates_enabled=True,
                        gate_broker=broker,
                        gate=plan_gate,
                        gate_decision=decisions.get(GATE_KIND_PLAN, {}),
                        scheme_gate=scheme_gate,
                        scheme_gate_decision=decisions.get(GATE_KIND_SCHEME, {}),
                    )
                )

            elif msg_type == "cancel":
                cancel_flag["cancelled"] = True
                broker.cancel_all()
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                await ws.send_json({"type": "cancelled"})

            elif msg_type == "delete_session":
                session_id = _as_str(msg.get("session_id"))
                if not is_valid_session_id(session_id):
                    await ws.send_json({"type": "error", "message": "Invalid session id."})
                    continue
                try:
                    delete_session(session_id)
                    await ws.send_json({
                        "type": "session_deleted",
                        "session_id": session_id,
                    })
                except Exception:
                    logger.error("Failed to delete session", exc_info=True)
                    await ws.send_json({
                        "type": "error",
                        "message": "Could not delete this session. Please try again.",
                    })

            elif msg_type == "export_session":
                session_id = _as_str(msg.get("session_id"))
                if not is_valid_session_id(session_id):
                    await ws.send_json({"type": "error", "message": "Invalid session id."})
                    continue
                try:
                    data = load_last_session(session_id)
                except Exception:
                    logger.error("Failed to export session", exc_info=True)
                    data = None
                if data:
                    await ws.send_json({
                        "type": "session_export",
                        "session_id": session_id,
                        "data": data,
                    })
                else:
                    await ws.send_json({
                        "type": "error",
                        "message": "No saved session found.",
                    })

            else:
                await ws.send_json({
                    "type": "error",
                    "message": "Unsupported message.",
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected")
        broker.cancel_all()
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()
    except Exception:
        logger.error("WebSocket handler failed", exc_info=True)
        try:
            await ws.send_json({
                "type": "error",
                "message": "Something went wrong on our side. Please try again.",
            })
        except Exception:
            pass
        broker.cancel_all()
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()
