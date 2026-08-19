import asyncio
import sys
import logging
from backend.agents.research import research_agent

logging.basicConfig(level=logging.INFO)

async def test():
    # Fix unicode printing in Windows console
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    print("Testing research agent with a standard query...")
    result = await research_agent("AI voice generator for teachers")
    print("\n--- RESULT ---\n")
    print(result)

asyncio.run(test())
