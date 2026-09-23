"""
ws_market.py — WebSocket endpoint for the market research workflow.

Messages handled:
- `start`: begin a run (optionally resume a prior session via session_id)
- `cancel`: cancel the running workflow
- `delete_session`: GDPR right-to-delete
- `export_session`: export stored session data
"""
import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.core.ws import SafeWebSocket
from backend.workflows.executor import run_research_workflow

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/market")
async def market_research_websocket(websocket: WebSocket):
    await websocket.accept()
    ws = SafeWebSocket(websocket)

    cancel_flag = {"cancelled": False}
    workflow_task = None

    try:
        while True:
            msg = await ws.receive_json()
            msg_type = msg.get("type")

            if msg_type == "start":
                topic = msg.get("topic", "").strip()
                max_steps = min(int(msg.get("max_steps", 4)), 6)
                session_id = msg.get("session_id", "").strip()

                if not topic:
                    await ws.send_json({"type": "error", "message": "Topic is empty."})
                    continue

                cancel_flag["cancelled"] = False

                # Load prior session context for continuity.
                session_context = ""
                if session_id:
                    try:
                        from backend.core.memory import build_resume_context, load_last_session
                        prior = load_last_session(session_id)
                        if prior:
                            session_context = build_resume_context(prior)
                            await ws.send_json({
                                "type": "resume_available",
                                "session_id": session_id,
                                "previous_topic": prior.get("topic", ""),
                                "summary": session_context[:300],
                            })
                    except ImportError:
                        pass  # memory module not present
                    except Exception:
                        pass  # never block a run because of memory errors

                # Cancel the previous task if still running.
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()

                workflow_task = asyncio.create_task(
                    run_research_workflow(
                        topic, max_steps, ws, cancel_flag,
                        session_context=session_context,
                        session_id=session_id,
                    )
                )

            elif msg_type == "cancel":
                cancel_flag["cancelled"] = True
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                await ws.send_json({"type": "cancelled"})

            elif msg_type == "delete_session":
                session_id = msg.get("session_id", "").strip()
                try:
                    from backend.core.memory import delete_session
                    delete_session(session_id)
                    await ws.send_json({
                        "type": "session_deleted",
                        "session_id": session_id,
                    })
                except ImportError:
                    await ws.send_json({
                        "type": "error",
                        "message": "Memory module not available.",
                    })

            elif msg_type == "export_session":
                session_id = msg.get("session_id", "").strip()
                try:
                    from backend.core.memory import load_last_session
                    data = load_last_session(session_id)
                    if data:
                        await ws.send_json({
                            "type": "session_export",
                            "session_id": session_id,
                            "data": data,
                        })
                    else:
                        await ws.send_json({
                            "type": "error",
                            "message": f"No session found for id: {session_id}",
                        })
                except ImportError:
                    await ws.send_json({
                        "type": "error",
                        "message": "Memory module not available.",
                    })

            else:
                await ws.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("Client disconnected")
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()