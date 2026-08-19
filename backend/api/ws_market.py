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
                if not topic:
                    await websocket.send_json({"type": "error", "message": "Topic is empty."})
                    continue
                cancel_flag["cancelled"] = False
                
                # Cancel previous task if still running
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                    
                import asyncio
                workflow_task = asyncio.create_task(
                    run_research_workflow(topic, max_steps, websocket, cancel_flag)
                )
            elif msg_type == "cancel":
                cancel_flag["cancelled"] = True
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                await websocket.send_json({"type": "cancelled"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})
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
