"""
LLM client for OpenRouter.

Phase 1b additions:
  - Request-level in-memory cache (keyed on sha256(messages + candidates + max_tokens))
  - Per-process model blacklist: skip 429/402 and "No endpoints found" 404s for this process
  - Optional agent_hint kwarg auto-applies per-agent token budgets
  - SESSION_TOKEN_USAGE accumulates approx token count per WebSocket session
  - reset_session_state() clears cache + counter between runs

Phase 6 addition:
  - API key rotation: if OPENROUTER_API_KEY_2 is set, every model attempt is tried
    first with key 1, then with key 2 before giving up on that model.
    Gives effectively double the free-tier quota without any agent changes.
    Key rotation is tracked separately from model blacklisting.
"""
import asyncio
import hashlib
import json
import logging
import os
from typing import Dict, List, Optional

import httpx

# Module-level so tests can monkey-patch them directly (existing test pattern)
from backend.core.config import OPENROUTER_API_KEY, OPENROUTER_API_KEY_2, OPENROUTER_BASE_URL, MODEL, FALLBACK_MODELS

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

# --------------------------------------------------------------------------- #
# Per-agent default token budgets                                               #
# Keeps LLM costs low. Caller can override by passing max_tokens explicitly.  #
# --------------------------------------------------------------------------- #
AGENT_TOKEN_BUDGETS: Dict[str, int] = {
    "planner":     300,   # just a list of strings
    "research":    400,   # concise bullet synthesis
    "analyst":     450,   # tables + bullets
    "opportunity": 350,   # 3-5 ranked items
    "writer":      600,   # full markdown report
    "editor":      600,   # polished markdown
    "decide":      120,   # agent routing JSON (legacy; no longer used)
    "default":     500,
}


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


async def call_llm(
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 500,
    agent_hint: Optional[str] = None,
) -> str:
    """
    Call OpenRouter with fallback, request-level caching, session blacklisting,
    and per-agent token budgeting.

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

    # Hard ceiling to protect free-tier quotas
    max_tokens = min(max_tokens, 1200)

    api_key = OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")
    api_key_2 = OPENROUTER_API_KEY_2 or os.getenv("OPENROUTER_API_KEY_2", "")
    base_url = OPENROUTER_BASE_URL or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is not configured. Check backend/.env or deployment env vars."
        )

    # Build deduplicated API key list (key 1 always first; key 2 appended if set)
    api_keys: List[str] = [api_key]
    if api_key_2 and api_key_2 != api_key:
        api_keys.append(api_key_2)
        logger.debug(f"[LLM] Key rotation active — {len(api_keys)} API keys available.")

    # Build deduplicated candidate list, respecting test-time monkey-patching
    import backend.core.llm_client as _self
    candidates: List[str] = []
    for m in [_self.MODEL] + list(_self.FALLBACK_MODELS):
        if m and m not in candidates and m not in _model_blacklist:
            candidates.append(m)

    if not candidates:
        raise ValueError(
            f"All candidate models are blacklisted: {_model_blacklist}. "
            "Restart the server to reset, or update FALLBACK_MODELS in config."
        )

    # Cache lookup
    ck = _cache_key(messages, candidates, max_tokens)
    if ck in _response_cache:
        logger.info(f"[LLM] Cache HIT (key={ck[:12]}...)")
        return _response_cache[ck]


    # Approximate input token cost
    input_text = " ".join(m.get("content", "") for m in messages)
    SESSION_TOKEN_USAGE["input"] += _approx_tokens(input_text)

    last_exception: Optional[Exception] = None

    async with httpx.AsyncClient(timeout=120.0) as client:
        for model in candidates:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }

            # ── Key rotation loop ────────────────────────────────────────────
            # For each model, try key1 then key2 before blacklisting the model.
            # A 429/402 on key1 → immediately retry same model with key2.
            # A 429/402 on key2 too → blacklist the model and move on.
            succeeded = False
            for key_idx, active_key in enumerate(api_keys):
                if succeeded:
                    break
                key_label = f"key{key_idx + 1}"
                headers = {
                    "Authorization": f"Bearer {active_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://market-research-agent.app",
                    "X-Title": "Market Research Agent",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                }

                for attempt in range(3):
                    logger.info(
                        f"[LLM] model={model} {key_label} attempt={attempt+1} max_tokens={max_tokens}"
                    )
                    try:
                        response = await client.post(
                            f"{base_url}/chat/completions",
                            headers=headers,
                            json=payload,
                        )

                        if response.status_code == 200:
                            data = response.json()
                            choices = data.get("choices", [])
                            if choices:
                                content = choices[0]["message"].get("content")
                                if content is not None:
                                    out_tokens = _approx_tokens(content)
                                    SESSION_TOKEN_USAGE["output"] += out_tokens
                                    SESSION_TOKEN_USAGE["total"] = (
                                        SESSION_TOKEN_USAGE["input"] + SESSION_TOKEN_USAGE["output"]
                                    )
                                    _response_cache[ck] = content
                                    logger.info(
                                        f"[LLM] Success via {model} ({key_label}) | "
                                        f"session_tokens~{SESSION_TOKEN_USAGE['total']}"
                                    )
                                    succeeded = True
                                    return content
                                else:
                                    logger.warning(f"[LLM] {model} {key_label}: content=None -- {data}")
                                    last_exception = ValueError(f"None content from {model}")
                                    break  # try next key
                            else:
                                logger.warning(f"[LLM] {model} {key_label}: no choices -- {data}")
                                last_exception = ValueError(f"No choices from {model}")
                                break  # try next key

                        elif response.status_code in (429, 402):
                            remaining_keys = len(api_keys) - key_idx - 1
                            logger.warning(
                                f"[LLM] {model} {key_label} -> {response.status_code} "
                                f"(rate-limited). {remaining_keys} key(s) still available for this model."
                            )
                            last_exception = ValueError(f"{response.status_code} on {model} ({key_label})")
                            break  # stop retrying this key — outer loop tries next key

                        elif response.status_code == 404:
                            err_text = response.text[:300]
                            if "No endpoints found" in err_text or "unavailable" in err_text.lower():
                                logger.warning(
                                    f"[LLM] {model} {key_label} -> 404 (no endpoints). Blacklisting model."
                                )
                                _model_blacklist.add(model)
                                # No point trying key2 for a down model — break key loop too
                                key_idx = len(api_keys)  # signal to skip remaining keys
                            else:
                                logger.warning(f"[LLM] {model} {key_label} -> 404: {err_text}")
                            last_exception = ValueError(f"OpenRouter 404 on {model}: {err_text}")
                            break

                        elif response.status_code in (400, 401, 403):
                            err_text = response.text[:200]
                            logger.warning(f"[LLM] {model} {key_label} -> {response.status_code}: {err_text}")
                            last_exception = ValueError(
                                f"OpenRouter {response.status_code} on {model}: {err_text}"
                            )
                            break  # non-retryable per-key; try next key

                        else:
                            err_text = response.text[:200]
                            logger.warning(
                                f"[LLM] {model} {key_label} -> {response.status_code}: {err_text} "
                                f"(attempt {attempt+1}/3)"
                            )
                            last_exception = ValueError(
                                f"OpenRouter {response.status_code} on {model}: {err_text}"
                            )
                            await asyncio.sleep(1)

                    except (httpx.TimeoutException, httpx.ConnectError) as e:
                        logger.warning(f"[LLM] {model} {key_label} network error: {e} (attempt {attempt+1}/3)")
                        last_exception = e
                        await asyncio.sleep(1)

                    except Exception as e:
                        logger.error(f"[LLM] {model} {key_label} unexpected error: {e}")
                        last_exception = e
                        await asyncio.sleep(1)

            # All keys exhausted for this model without success → blacklist it
            if not succeeded and model not in _model_blacklist:
                _model_blacklist.add(model)
                logger.warning(
                    f"[LLM] {model} failed on all {len(api_keys)} key(s). Blacklisting for this session."
                )

    if last_exception:
        raise last_exception
    raise ValueError("All candidate LLM models and API keys failed.")
