import httpx
from typing import List, Dict, Any
from backend.core.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODEL

async def call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://market-research-agent.app",
        "X-Title": "Market Research Agent",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 2048,
    }
    print(f"Calling LLM: {OPENROUTER_BASE_URL}/chat/completions")
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                print(f"Error Response: {response.text}")
                raise ValueError(f"OpenRouter API Error (Status {response.status_code}): {response.text}")
            response.raise_for_status()
            data = response.json()
            if "choices" not in data:
                print(f"OpenRouter Error: {data}")
                raise ValueError(f"OpenRouter returned no choices: {data}")
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"LLM Call failed: {str(e)}")
            raise e
