"""
ws_market.py — WebSocket endpoint for the market research workflow.

Phase 1 additions:
  - Accept optional session_id in "start" message (Phase 2 hook, no-op in Phase 1)
  - Pass session_context="" to run_research_workflow (wired in Phase 2)

Phase 2 additions (stubs wired here, implemented in backend/core/memory.py):
  - On connect, if session_id provided & prior session exists → send "resume_available" event

Phase 3 additions:
  - "delete_session" message type
  - "export_session" message type
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.workflows.executor import run_research_workflow

router = APIRouter()


@router.websocket("/ws/market")
async def market_research_websocket(websocket: WebSocket):
    await websocket.accept()
    cancel_flag = {"cancelled": False}
    workflow_task = None

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "start":
                topic = msg.get("topic", "").strip()
                max_steps = min(int(msg.get("max_steps", 4)), 6)
                session_id = msg.get("session_id", "").strip()

                if not topic:
                    await websocket.send_json({"type": "error", "message": "Topic is empty."})
                    continue

                cancel_flag["cancelled"] = False

                # ── Phase 2 hook: load prior session context ──────────────
                session_context = ""
                if session_id:
                    try:
                        from backend.core.memory import load_last_session, build_resume_context
                        prior = load_last_session(session_id)
                        if prior:
                            session_context = build_resume_context(prior)
                            await websocket.send_json({
                                "type": "resume_available",
                                "session_id": session_id,
                                "previous_topic": prior.get("topic", ""),
                                "summary": session_context[:300],
                            })
                    except ImportError:
                        pass  # memory module not yet present (Phase 1 only)
                    except Exception:
                        pass  # don't block a run because of memory errors

                # Cancel previous task if still running
                import asyncio
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()

                workflow_task = asyncio.create_task(
                    run_research_workflow(
                        topic, max_steps, websocket, cancel_flag,
                        session_context=session_context,
                        session_id=session_id,
                    )
                )

                # ── Phase 2 hook: save session after completion ───────────
                if session_id:
                    async def _save_on_done(task, sid, t):
                        try:
                            result = await task
                        except Exception:
                            return
                        # save handled inside executor via memory module (Phase 2)

            elif msg_type == "cancel":
                cancel_flag["cancelled"] = True
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                await websocket.send_json({"type": "cancelled"})

            elif msg_type == "delete_session":
                # Phase 3: handled here when memory module is present
                session_id = msg.get("session_id", "").strip()
                try:
                    from backend.core.memory import delete_session
                    delete_session(session_id)
                    await websocket.send_json({
                        "type": "session_deleted",
                        "session_id": session_id,
                    })
                except ImportError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Memory module not available (Phase 3 not yet implemented).",
                    })

            elif msg_type == "export_session":
                # Phase 3: handled here when memory module is present
                session_id = msg.get("session_id", "").strip()
                try:
                    from backend.core.memory import load_last_session
                    data = load_last_session(session_id)
                    if data:
                        await websocket.send_json({
                            "type": "session_export",
                            "session_id": session_id,
                            "data": data,
                        })
                    else:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"No session found for id: {session_id}",
                        })
                except ImportError:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Memory module not available (Phase 3 not yet implemented).",
                    })

            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {msg_type}",
                })

    except WebSocketDisconnect:
        print("Client disconnected")
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
        if workflow_task and not workflow_task.done():
            workflow_task.cancel()
