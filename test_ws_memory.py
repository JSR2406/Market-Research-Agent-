import asyncio
import websockets
import json
import sys

async def test_websocket_memory():
    uri = "ws://localhost:8000/ws/market"
    session_id = "test-session-123"
    topic = "AI in Education"
    
    # Run 1: Create session
    print("--- Run 1: Creating session ---")
    try:
        async with websockets.connect(uri) as websocket:
            request = {
                "type": "start",
                "topic": topic,
                "max_steps": 2,
                "session_id": session_id
            }
            await websocket.send(json.dumps(request))
            
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                print(f"Received: {data['type']}")
                if data['type'] == 'error':
                    print(f"Error: {data.get('message')}")
                    break
                elif data['type'] == 'done':
                    print("Run 1 completed.")
                    break
                elif data['type'] == 'cancelled':
                    break
    except Exception as e:
        print(f"Run 1 Connection failed: {e}")
        return

    # Run 2: Reconnect with same session_id and check for resume_available
    print("\n--- Run 2: Checking resume_available ---")
    try:
        async with websockets.connect(uri) as websocket:
            request = {
                "type": "start",
                "topic": "AI in Education 2.0",
                "max_steps": 1,
                "session_id": session_id
            }
            await websocket.send(json.dumps(request))
            
            received_resume = False
            while True:
                response = await websocket.recv()
                data = json.loads(response)
                print(f"Received: {data['type']}")
                if data['type'] == 'resume_available':
                    print(f"Successfully received resume_available event: previous_topic={data.get('previous_topic')}")
                    received_resume = True
                elif data['type'] == 'error':
                    print(f"Error: {data.get('message')}")
                    break
                elif data['type'] == 'done':
                    print("Run 2 completed.")
                    break
                elif data['type'] == 'cancelled':
                    break
                    
            if not received_resume:
                print("FAILED: Did not receive resume_available event.")
                sys.exit(1)
                
    except Exception as e:
        print(f"Run 2 Connection failed: {e}")
        return

    # Run 3: Export and Delete
    print("\n--- Run 3: Testing Export and Delete ---")
    try:
        async with websockets.connect(uri) as websocket:
            # Export
            await websocket.send(json.dumps({
                "type": "export_session",
                "session_id": session_id
            }))
            
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Export received type: {data['type']}")
            if data['type'] == 'session_export':
                print(f"Export success. Topic: {data['data'].get('topic')}")
            else:
                print("FAILED: Export failed.")
                sys.exit(1)
                
            # Delete
            await websocket.send(json.dumps({
                "type": "delete_session",
                "session_id": session_id
            }))
            
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Delete received type: {data['type']}")
            if data['type'] != 'session_deleted':
                print("FAILED: Delete failed.")
                sys.exit(1)
                
            # Verify Delete
            await websocket.send(json.dumps({
                "type": "export_session",
                "session_id": session_id
            }))
            
            response = await websocket.recv()
            data = json.loads(response)
            print(f"Verify delete received type: {data['type']}")
            if data['type'] == 'error' and 'No session found' in data['message']:
                print("Verify delete success.")
            else:
                print("FAILED: Session still exists after delete.")
                sys.exit(1)
                
    except Exception as e:
        print(f"Run 3 Connection failed: {e}")
        return

    print("\nALL PHASE 2 & 3 TESTS PASSED")

if __name__ == "__main__":
    asyncio.run(test_websocket_memory())
