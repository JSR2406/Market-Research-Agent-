import asyncio
import backend.core.llm_client as llm_client
import backend.core.config as config

async def test_fallbacks():
    # Force a 402 error by using a model that we know doesn't exist to simulate a hard fail,
    # then ensure the free models pick it up.
    print(f"Original models: {[config.MODEL] + config.FALLBACK_MODELS}")
    llm_client.MODEL = "invalid/model-402-simulator"
    llm_client.FALLBACK_MODELS = [
        "invalid/model-2",
        "meta-llama/llama-3.1-8b-instruct:free",
    ]
    
    try:
        print("Testing robust fallback...")
        response = await llm_client.call_llm([{"role": "user", "content": "Say 'Fallback successful!'"}] * 1)
        print("Final Output:", response)
    except Exception as e:
        print("Failure:", str(e))

asyncio.run(test_fallbacks())
