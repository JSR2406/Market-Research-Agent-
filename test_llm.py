import asyncio
from backend.core.llm_client import call_llm

async def test():
    try:
        response = await call_llm([{"role": "user", "content": "Say hello"}])
        print("Success:", response)
    except Exception as e:
        print("Failure:", str(e))

asyncio.run(test())
