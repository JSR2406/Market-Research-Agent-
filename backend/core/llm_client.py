"""
LLM client with multi-provider support (Ollama, Hugging Face, OpenRouter).

Phase 1b additions:
  - Request-level in-memory cache (keyed on sha256(messages + candidates + max_tokens))
  - Per-process model blacklist: skip 429/402 and "No endpoints found" 404s for this process
  - Optional agent_hint kwarg auto-applies per-agent token budgets
  - SESSION_TOKEN_USAGE accumulates approx token count per WebSocket session
  - reset_session_state() clears cache + counter between runs

Phase 2 additions:
  - Multi-provider support: Ollama (local), Hugging Face Inference API, OpenRouter
  - Provider priority order configurable via LLM_PROVIDER_PRIORITY
  - Automatic fallback between providers
  - No token limits when using local Ollama
"""
import asyncio
import hashlib
import json
import logging
import os
from typing import Dict, List, Optional

import httpx

# Module-level so tests can monkey-patch them directly (existing test pattern)
from backend.core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_API_KEY_2,
    OPENROUTER_BASE_URL,
    MODEL,
    FALLBACK_MODELS,
    OLLAMA_BASE_URL,
    OLLAMA_MODEL,
    OLLAMA_FALLBACK_MODELS,
    HF_API_TOKEN,
    HF_MODEL,
    HF_FALLBACK_MODELS,
    LLM_PROVIDER_PRIORITY,
    AGENT_TOKEN_BUDGETS,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Per-process model blacklist                                                   #
# Models added here are skipped for the lifetime of this process.              #
# Populated when 429/402 or "No endpoints found" 404 is received.              #
# --------------------------------------------------------------------------- #
_model_blacklist: set[str] = set()

# --------------------------------------------------------------------------- #
# Request-level response cache                                                  #
# dict[sha256_hex -> str]  -- cleared on each new WS session                  #
# --------------------------------------------------------------------------- #
_response_cache: Dict[str, str] = {}

# --------------------------------------------------------------------------- #
# Session-level approximate token counter                                       #
# Approx via len(text) // 4. Reset between sessions.                           #
# --------------------------------------------------------------------------- #
SESSION_TOKEN_USAGE: Dict[str, int] = {"input": 0, "output": 0, "total": 0}


def reset_session_state() -> None:
    """Clear token counter. Call at the start of each WS workflow run. Cache is preserved for rehearsal."""
    SESSION_TOKEN_USAGE["input"] = 0
    SESSION_TOKEN_USAGE["output"] = 0
    SESSION_TOKEN_USAGE["total"] = 0
    logger.info("Session state reset: token counter zeroed.")


def _cache_key(messages: List[Dict[str, str]], candidates: List[str], max_tokens: int) -> str:
    payload = json.dumps(
        {"messages": messages, "candidates": candidates, "max_tokens": max_tokens},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ─────────────────────────────────────────────────────────────────────────────
# Provider-specific implementations
# ─────────────────────────────────────────────────────────────────────────────

async def _call_ollama(
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    model: str,
) -> Optional[str]:
    """Call Ollama local API."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            }
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            if response.status_code == 200:
                data = response.json()
                content = data.get("message", {}).get("content")
                if content:
                    logger.info(f"[LLM/Ollama] Success via {model}")
                    return content
                logger.warning(f"[LLM/Ollama] {model}: empty content")
            elif response.status_code == 404:
                err = response.text[:200]
                if "not found" in err.lower() or "model" in err.lower():
                    logger.warning(f"[LLM/Ollama] {model} not found locally. Blacklisting.")
                    _model_blacklist.add(model)
            else:
                logger.warning(f"[LLM/Ollama] {model} -> {response.status_code}: {response.text[:200]}")
    except httpx.ConnectError:
        logger.warning(f"[LLM/Ollama] Cannot connect to {OLLAMA_BASE_URL}. Is Ollama running?")
    except httpx.TimeoutException:
        logger.warning(f"[LLM/Ollama] Timeout calling {model}")
    except Exception as e:
        logger.warning(f"[LLM/Ollama] {model} error: {e}")
    return None


async def _call_huggingface(
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    model: str,
) -> Optional[str]:
    """Call Hugging Face Inference API."""
    try:
        # Convert messages to HF text-completion format (model-agnostic)
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"SYSTEM: {content}\n\n"
            elif role == "user":
                prompt += f"USER: {content}\n\n"
            elif role == "assistant":
                prompt += f"ASSISTANT: {content}\n\n"
        prompt += "ASSISTANT: "

        headers = {"Content-Type": "application/json"}
        if HF_API_TOKEN:
            headers["Authorization"] = f"Bearer {HF_API_TOKEN}"

        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": temperature,
                "max_new_tokens": max_tokens,
                "return_full_text": False,
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers=headers,
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    content = data[0].get("generated_text", "")
                    if content:
                        logger.info(f"[LLM/HF] Success via {model}")
                        return content.strip()
                logger.warning(f"[LLM/HF] {model}: unexpected response format: {data}")
            elif response.status_code == 404:
                logger.warning(f"[LLM/HF] {model} not found. Blacklisting.")
                _model_blacklist.add(model)
            elif response.status_code == 503:
                # Model loading
                logger.warning(f"[LLM/HF] {model} is loading, waiting...")
                await asyncio.sleep(10)
                # Retry once
                response = await client.post(
                    f"https://api-inference.huggingface.co/models/{model}",
                    headers=headers,
                    json=payload,
                )
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and data:
                        content = data[0].get("generated_text", "")
                        if content:
                            logger.info(f"[LLM/HF] Success via {model} (after loading)")
                            return content.strip()
            elif response.status_code in (429, 402):
                logger.warning(f"[LLM/HF] {model} rate limited")
                _model_blacklist.add(model)
            else:
                logger.warning(f"[LLM/HF] {model} -> {response.status_code}: {response.text[:200]}")
    except Exception as e:
        logger.warning(f"[LLM/HF] {model} error: {e}")
    return None


async def _call_openrouter(
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    model: str,
    api_key: str,
) -> Optional[str]:
    """Call OpenRouter API with a specific API key."""
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://market-research-agent.app",
            "X-Title": "Market Research Agent",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    content = choices[0]["message"].get("content")
                    if content is not None:
                        logger.info(f"[LLM/OpenRouter] Success via {model}")
                        return content
                    logger.warning(f"[LLM/OpenRouter] {model}: content=None")
                else:
                    logger.warning(f"[LLM/OpenRouter] {model}: no choices")
            elif response.status_code in (429, 402):
                logger.warning(f"[LLM/OpenRouter] {model} rate limited")
            elif response.status_code == 404:
                err_text = response.text[:300]
                if "No endpoints found" in err_text or "unavailable" in err_text.lower():
                    logger.warning(f"[LLM/OpenRouter] {model} no endpoints. Blacklisting.")
                    _model_blacklist.add(model)
                else:
                    logger.warning(f"[LLM/OpenRouter] {model} -> 404: {err_text}")
            else:
                logger.warning(f"[LLM/OpenRouter] {model} -> {response.status_code}: {response.text[:200]}")
    except Exception as e:
        logger.warning(f"[LLM/OpenRouter] {model} error: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

async def call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 500,
    agent_hint: Optional[str] = None,
) -> str:
    """
    Call LLM with multi-provider fallback.

    Parameters
    ----------
    messages    : standard OpenAI-style message list
    temperature : sampling temperature
    max_tokens  : hard cap on output tokens; if 500 (default) and agent_hint given,
                  the per-agent budget from AGENT_TOKEN_BUDGETS is used instead
    agent_hint  : optional name (planner/research/analyst/opportunity/writer/editor)
    """
    # Apply agent budget only when caller left max_tokens at its sentinel default
    if agent_hint and max_tokens == 500:
        max_tokens = AGENT_TOKEN_BUDGETS.get(agent_hint, AGENT_TOKEN_BUDGETS["default"])

    # Cloud providers get a hard ceiling to protect free-tier quotas.
    # Local providers (Ollama) keep the caller's budget — no arbitrary cap.
    cloud_max_tokens = min(max_tokens, 1200)

    # Build all candidate models across providers
    all_candidates: List[tuple[str, str]] = []  # (provider, model)
    seen: set[tuple[str, str]] = set()

    for provider in LLM_PROVIDER_PRIORITY:
        if provider == "ollama":
            for m in OLLAMA_FALLBACK_MODELS:
                if m and (provider, m) not in seen and m not in _model_blacklist:
                    seen.add((provider, m))
                    all_candidates.append((provider, m))
        elif provider == "huggingface":
            for m in HF_FALLBACK_MODELS:
                if m and (provider, m) not in seen and m not in _model_blacklist:
                    seen.add((provider, m))
                    all_candidates.append((provider, m))
        elif provider == "openrouter":
            api_key = OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
            api_key_2 = OPENROUTER_API_KEY_2 or os.getenv("OPENROUTER_API_KEY_2", "")
            if api_key:
                for m in [MODEL] + list(FALLBACK_MODELS):
                    if m and (provider, m) not in seen and m not in _model_blacklist:
                        seen.add((provider, m))
                        all_candidates.append((provider, m))
            else:
                logger.warning("[LLM] OpenRouter in priority but no API key configured")

    if not all_candidates:
        raise ValueError(
            f"All candidate models are blacklisted: {_model_blacklist}. "
            "Restart the server to reset, or update model lists in config."
        )

    # Cache lookup
    candidate_models = [m for _, m in all_candidates]
    ck = _cache_key(messages, candidate_models, max_tokens)
    if ck in _response_cache:
        logger.info(f"[LLM] Cache HIT (key={ck[:12]}...)")
        return _response_cache[ck]

    # Approximate input token cost
    input_text = " ".join(m.get("content", "") for m in messages)
    SESSION_TOKEN_USAGE["input"] += _approx_tokens(input_text)

    last_exception: Optional[Exception] = None

    # Try each provider/model combination
    for provider, model in all_candidates:
        content = None
        # Local providers (Ollama) are not token-capped; cloud are.
        budget = cloud_max_tokens if provider != "ollama" else max_tokens

        if provider == "ollama":
            content = await _call_ollama(messages, temperature, budget, model)
        elif provider == "huggingface":
            content = await _call_huggingface(messages, temperature, budget, model)
        elif provider == "openrouter":
            api_key = OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
            api_key_2 = OPENROUTER_API_KEY_2 or os.getenv("OPENROUTER_API_KEY_2", "")
            keys = [api_key]
            if api_key_2 and api_key_2 != api_key:
                keys.append(api_key_2)

            for key in keys:
                content = await _call_openrouter(messages, temperature, budget, model, key)
                if content:
                    break
                # If rate limited on first key, try second
                if not content and key == keys[0] and len(keys) > 1:
                    continue
                break

        if content:
            out_tokens = _approx_tokens(content)
            SESSION_TOKEN_USAGE["output"] += out_tokens
            SESSION_TOKEN_USAGE["total"] = (
                SESSION_TOKEN_USAGE["input"] + SESSION_TOKEN_USAGE["output"]
            )
            _response_cache[ck] = content
            logger.info(
                f"[LLM] Success via {provider}/{model} | "
                f"session_tokens~{SESSION_TOKEN_USAGE['total']}"
            )
            return content

        # Model failed, continue to next
        last_exception = ValueError(f"{provider}/{model} failed")

    if last_exception:
        raise last_exception
    raise ValueError("All candidate LLM models and providers failed.")