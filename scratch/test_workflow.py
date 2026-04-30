import asyncio
import sys
import os

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.agents.executor import run_research_workflow

class MockWebSocket:
    async def send_json(self, data):
        print(f"WS EVENT: {data.get('type')} - {data.get('agent', '')}")
        if data.get("type") == "error":
            print(f"ERROR: {data.get('message')}")

async def main():
    topic = "AI productivity tools for students in India 2026"
    max_steps = 4
    ws = MockWebSocket()
    cancel_flag = {"cancelled": False}
    
    print(f"Starting research for: {topic}")
    async for _ in run_research_workflow(topic, max_steps, ws, cancel_flag):
        pass
    print("Research complete.")

if __name__ == "__main__":
    asyncio.run(main())
