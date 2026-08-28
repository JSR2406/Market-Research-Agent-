import asyncio
import websockets
import json
import sys

async def test_websocket():
    uri = "ws://localhost:8001/ws/market"
    try:
        async with websockets.connect(uri) as websocket:
            request = {
                "type": "start",
                "topic": "I sell vegetables, make about ₹400/day",
                "max_steps": 5
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
                    print("Workflow completed successfully.")
                    print("\n--- FINAL REPORT ---\n")
                    with open("test_output.md", "w", encoding="utf-8") as f:
                        f.write(data.get('final_report'))
                    print("Report saved to test_output.md")
                    break
                elif data['type'] == 'cancelled':
                    print("Workflow cancelled.")
                    break
                
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
