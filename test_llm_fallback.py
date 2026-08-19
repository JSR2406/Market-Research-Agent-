import asyncio
import backend.core.llm_client as llm_client

async def test():
    # Force a bad model to trigger fallback
    llm_client.MODEL = "invalid/model"
    llm_client.FALLBACK_MODELS = [
        "invalid/model",
        "openrouter/free"
    ]
    
    try:
        response = await llm_client.call_llm([{"role": "user", "content": "Say hello"}])
        print("Success:", response)
    except Exception as e:
        print("Failure:", str(e))

asyncio.run(test())
