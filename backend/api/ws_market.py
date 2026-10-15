"""
ws_market.py — WebSocket endpoint for the market research workflow.

Messages handled:
- `start`: begin a run (optionally resume a prior session via session_id)
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

from backend.core.config import ALLOWED_ORIGINS
from backend.core.intake import normalize_intake
from backend.core.memory import (
    build_resume_context,
    delete_session,
    is_valid_session_id,
    load_last_session,
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
                            await ws.send_json({
                                "type": "resume_available",
                                "session_id": session_id,
                                "previous_topic": prior.get("topic", ""),
                                "summary": session_context[:300],
                            })
                    except Exception:
                        logger.warning("Failed to load resume context", exc_info=True)
                        # never block a run because of memory errors

                # Cancel the previous task if still running.
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()

                workflow_task = asyncio.create_task(
                    run_research_workflow(
                        topic, max_steps, ws, cancel_flag,
                        session_context=session_context,
                        session_id=session_id,
                        profile=profile,
                        intake=intake,
                        lang=lang,
                    )
                )

            elif msg_type == "cancel":
                cancel_flag["cancelled"] = True
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
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()
