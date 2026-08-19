import os
import httpx
from typing import List, Dict, Any
from backend.core.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL, MODEL, FALLBACK_MODELS

async def call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 600,
) -> str:
    # Get current key dynamically from config or environment
    api_key = OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
    base_url = OPENROUTER_BASE_URL or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not configured. Please check your backend/.env file.")

    # Deduplicate candidate models keeping order
    candidates = []
    for m in [MODEL] + FALLBACK_MODELS:
        if m and m not in candidates:
            candidates.append(m)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://market-research-agent.app",
        "X-Title": "Market Research Agent",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    last_exception = None

    import asyncio
    async with httpx.AsyncClient(timeout=120.0) as client:
        for model in candidates:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": min(max_tokens, 1200),
            }
            
            for attempt in range(3):
                print(f"Calling LLM ({model}) attempt {attempt+1}: {base_url}/chat/completions")
                try:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if "choices" in data and len(data["choices"]) > 0:
                            content = data["choices"][0]["message"].get("content")
                            if content is not None:
                                return content
                            else:
                                print(f"OpenRouter Error with model {model}: Content is None. {data}")
                                last_exception = ValueError(f"OpenRouter returned None content: {data}")
                                break
                        else:
                            print(f"OpenRouter Error with model {model}: {data}")
                            last_exception = ValueError(f"OpenRouter returned no choices: {data}")
                            break # No choices usually means the request itself is rejected due to policy, retry won't help
                    elif response.status_code == 429:
                        print(f"Rate limited on {model}, backing off...")
                        await asyncio.sleep(2 * (attempt + 1))
                        last_exception = ValueError("Rate limited (429)")
                    else:
                        err_msg = response.text
                        print(f"Model {model} returned status {response.status_code}: {err_msg}")
                        last_exception = ValueError(f"OpenRouter API Error (Status {response.status_code}): {err_msg}")
                        # Don't retry on 401, 400, 402, 403, or 404
                        if response.status_code in (400, 401, 402, 403, 404):
                            break
                        await asyncio.sleep(1)
                except Exception as e:
                    print(f"LLM Call failed for model {model}: {str(e)}")
                    last_exception = e
                    await asyncio.sleep(1)
                    
            if not isinstance(last_exception, (httpx.TimeoutException, httpx.ConnectError)) and not (isinstance(last_exception, ValueError) and "429" in str(last_exception)):
                # If we broke out or failed a non-retryable error, we can still try the next model
                pass

    if last_exception:
        raise last_exception
    raise ValueError("All candidate LLM models failed.")
