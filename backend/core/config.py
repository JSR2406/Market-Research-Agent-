import os
import sys
from dotenv import load_dotenv

# Always load from backend/.env relative to this file's location
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

# ──────────────────────────────────────────────────────────────────────────────
# OpenRouter (cloud, primary)
# ──────────────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEY_2: str = os.getenv("OPENROUTER_API_KEY_2", "")  # optional second key for rate-limit rotation
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

# Configured LLM model with fallbacks
MODEL: str = os.getenv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")

# Priority fallback models if primary model is unavailable or encounters API errors.
# Only verified, currently-serving OpenRouter models. Deprecated `:free` model IDs and
# retired preview models are excluded — they return 400/404 and waste the fallback chain.
FALLBACK_MODELS: list[str] = [
    MODEL,
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "openrouter/auto",
]

# ──────────────────────────────────────────────────────────────────────────────
# Ollama (local, free, no token limits)
# ──────────────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")  # small, fast, good for most tasks
OLLAMA_FALLBACK_MODELS: list[str] = [
    OLLAMA_MODEL,
    "llama3.2:3b",
    "qwen2.5:3b",
    "llama3.1:8b",
    "mistral:7b",
    "qwen2.5:7b",
    "gemma2:9b",
]

# ──────────────────────────────────────────────────────────────────────────────
# Hugging Face Inference API (cloud, free tier available)
# ──────────────────────────────────────────────────────────────────────────────
HF_API_TOKEN: str = os.getenv("HF_API_TOKEN", "")  # optional, higher rate limits with token
HF_MODEL: str = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
HF_FALLBACK_MODELS: list[str] = [
    HF_MODEL,
    "mistralai/Mistral-7B-Instruct-v0.3",
    "HuggingFaceH4/zephyr-7b-beta",
    "google/gemma-2-9b-it",
    "Intel/neural-chat-7b-v3-1",
]

# ──────────────────────────────────────────────────────────────────────────────
# Provider priority order (first successful wins)
# ──────────────────────────────────────────────────────────────────────────────
# Options: "openrouter", "ollama", "huggingface"
# Default: try local Ollama first (free, no limits), then Hugging Face, then OpenRouter
LLM_PROVIDER_PRIORITY: list[str] = [
    p.strip() for p in os.getenv("LLM_PROVIDER_PRIORITY", "ollama,huggingface,openrouter").split(",") if p.strip()
]

# ---------------------------------------------------------------------------
# Per-agent default token budgets
# Keeps LLM costs low. Caller can override by passing max_tokens explicitly.
# ---------------------------------------------------------------------------
AGENT_TOKEN_BUDGETS: dict[str, int] = {
    "planner":     300,   # just a list of strings
    "research":    400,   # concise bullet synthesis
    "analyst":     450,   # tables + bullets
    "opportunity": 350,   # 3-5 ranked items
    "writer":      600,   # full markdown report
    "editor":      600,   # polished markdown
    "simplifier":  200,   # very short plain-language summary
    "voice":       250,   # live voice advisor — short spoken answers
    "chat":        400,   # conversational chatbot — concise, with memory
    "supervisor":  300,   # agentic router — picks the next node (JSON decision)
    "critic":      400,   # reflection/self-critique of the draft advisory
    "default":     500,
}

# ──────────────────────────────────────────────────────────────────────────────
# Per-agent model selection
# Spreads LLM load across different models so a single model's free-tier quota
# is not exhausted by every agent in every run. Each agent leads with its own
# primary model (first entry); the global FALLBACK_MODELS chain is appended
# afterwards, so any agent still degrades gracefully if its primary 404s.
# NOTE: "chat" must keep an OPEN-SOURCE primary (project rule — no proprietary
# models for the chatbot).
# ──────────────────────────────────────────────────────────────────────────────
AGENT_OPENROUTER_MODELS: dict[str, list[str]] = {
    "planner":      ["qwen/qwen-2.5-72b-instruct"],
    "research":     ["google/gemini-2.5-flash"],
    "analyst":      ["meta-llama/llama-3.3-70b-instruct"],
    "opportunity":  ["deepseek/deepseek-chat"],
    "writer":       ["google/gemini-2.5-flash"],
    "editor":       ["meta-llama/llama-3.3-70b-instruct"],
    "simplifier":   ["openrouter/auto"],
    "voice":        ["openrouter/auto"],
    "chat":         ["mistralai/mistral-7b-instruct"],  # open-source
    "supervisor":   ["qwen/qwen-2.5-72b-instruct"],
    "critic":       ["deepseek/deepseek-chat"],
    "default":      [],
}

# ──────────────────────────────────────────────────────────────────────────────
# Agentic engine (LangGraph orchestration)
# ──────────────────────────────────────────────────────────────────────────────
# The advisory pipeline is a LangGraph StateGraph (see backend/agentic/). These
# knobs bound the autonomy: how many supervisor→worker cycles are allowed before
# the graph is forced to synthesize, and whether the reflection (self-critique)
# loop runs at all. Budgets keep a runaway ReAct loop from burning free-tier
# quota — the graph is deterministic-capped even when the LLM is creative.
AGENTIC_ENGINE_ENABLED: bool = os.getenv("AGENTIC_ENGINE_ENABLED", "true").strip().lower() in (
    "1", "true", "yes",
)
AGENTIC_MAX_ITERATIONS: int = int(os.getenv("AGENTIC_MAX_ITERATIONS", "8"))
AGENTIC_REFLECTION_ENABLED: bool = os.getenv("AGENTIC_REFLECTION_ENABLED", "true").strip().lower() in (
    "1", "true", "yes",
)
# When the graph can't reach a usable advisory it still emits the deterministic
# heuristic tier — never a blank report (offline guarantee).
AGENTIC_CHECKPOINTING: bool = os.getenv("AGENTIC_CHECKPOINTING", "true").strip().lower() in (
    "1", "true", "yes",
)

# ──────────────────────────────────────────────────────────────────────────────
# Human approval gates
# ──────────────────────────────────────────────────────────────────────────────
# A gate pauses the advisory run until the user approves it in the UI. It is
# OFF by default: gating every research step would be friction for a
# micro-entrepreneur, and the product promise is "your report, without a
# queue". Turn it on per run from the UI, or globally here for a deployment
# that wants every run reviewed. A run that never gets an answer parks — it is
# never silently approved.
GATES_ENABLED: bool = os.getenv("GATES_ENABLED", "false").strip().lower() in (
    "1", "true", "yes",
)
# How long a parked run waits for the user's decision before it parks on disk
# and waits to be resumed. Bounded so a forgotten tab cannot hold a worker.
GATE_WAIT_SECONDS: int = int(os.getenv("GATE_WAIT_SECONDS", "180"))

# ──────────────────────────────────────────────────────────────────────────────
# Real-time web research
# ──────────────────────────────────────────────────────────────────────────────
WEB_SEARCH_ENABLED: bool = os.getenv("WEB_SEARCH_ENABLED", "true").strip().lower() in (
    "1", "true", "yes",
)
WEB_SEARCH_MAX_RESULTS: int = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))

# ──────────────────────────────────────────────────────────────────────────────
# Voice/TTS settings
# ──────────────────────────────────────────────────────────────────────────────
ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

# Hugging Face TTS models (free, no API key required for public models)
HF_TTS_MODEL: str = os.getenv("HF_TTS_MODEL", "facebook/mms-tts-eng")  # text → audio, works out of the box
HF_TTS_FALLBACK_MODELS: list[str] = [
    HF_TTS_MODEL,
    "espnet/kan-bayashi_ljspeech_vits",
]

# Piper TTS — fully open-source, local, no API key (MIT). ONNX voices are
# downloaded once from Hugging Face (rhasspy/piper-voices) on first use and then
# cached under PIPER_VOICE_DIR; synthesis itself runs 100% offline after that.
# en = default English voice, hi = used automatically when the text contains
# Devanagari characters (the advisory is bilingual). Model downloads are lazy —
# the first /api/voice/speak warms the cache, all later calls are pure local.
PIPER_VOICE_DIR: str = os.getenv(
    "PIPER_VOICE_DIR",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "piper"),
)
PIPER_VOICE_EN: str = os.getenv("PIPER_VOICE_EN", "en_US-lessac-medium")
PIPER_VOICE_HI: str = os.getenv("PIPER_VOICE_HI", "hi_IN-pratham-medium")

# ──────────────────────────────────────────────────────────────────────────────
# LiveKit realtime voice (advisory voice agent)
# ──────────────────────────────────────────────────────────────────────────────
# LiveKit provides the realtime audio transport (WebRTC). The agent worker runs
# separately (backend/voice_agent/) and joins LIVEKIT_ADVISOR_ROOM; the browser
# joins the same room via a short-lived token from /api/voice/livekit-token.
# LiveKit Cloud: https://cloud.livekit.io (free tier) or self-host `lk-server`.
LIVEKIT_URL: str = os.getenv("LIVEKIT_URL", "")  # wss://<project>.livekit.cloud
LIVEKIT_API_KEY: str = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET: str = os.getenv("LIVEKIT_API_SECRET", "")
LIVEKIT_ADVISOR_ROOM: str = os.getenv("LIVEKIT_ADVISOR_ROOM", "advisory-room")

# ──────────────────────────────────────────────────────────────────────────────
# WhatsApp Cloud API (Meta) — OPTIONAL scaffold, activates when configured
# ──────────────────────────────────────────────────────────────────────────────
# Meta Developers → WhatsApp → API Setup. The webhook is served by
# backend/api/whatsapp.py (GET verifies, POST answers via chat_agent).
WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
# Meta app secret — used to verify X-Hub-Signature-256 on webhook POSTs.
# While unset the webhook still accepts posts (scaffold stays testable);
# once set, unsigned/forgeable payloads are rejected with 403.
WHATSAPP_APP_SECRET: str = os.getenv("WHATSAPP_APP_SECRET", "")

# ──────────────────────────────────────────────────────────────────────────────
# Browser origins allowed for CORS *and* the WebSocket handshake
# (cross-site WebSocket hijacking guard in backend/api/ws_market.py).
# ──────────────────────────────────────────────────────────────────────────────
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
    "http://localhost:3003,http://localhost:3004,http://localhost:3005,"
    "https://market-research-agent-neon.vercel.app",
)
ALLOWED_ORIGINS: list[str] = [o.strip().rstrip("/") for o in _raw_origins.split(",") if o.strip()]

# ──────────────────────────────────────────────────────────────────────────────
# Fail-fast guard
# ──────────────────────────────────────────────────────────────────────────────
# A missing API key causes silent 401s deep in workflows. Surface the error
# immediately at import time so uvicorn exits with a clear message instead of
# starting up in a permanently broken state.
#
# Skip the check during pytest / test runs so existing test scripts that patch
# the key after import can still load the module.
_in_test = "pytest" in sys.modules or os.getenv("PYTEST_RUNNING") == "1"

# Only require OpenRouter key if it's in the provider priority list
if "openrouter" in LLM_PROVIDER_PRIORITY and not OPENROUTER_API_KEY and not _in_test:
    print(
        "\n"
        "┌─────────────────────────────────────────────────────────────────┐\n"
        "│  FATAL: OPENROUTER_API_KEY is not set but 'openrouter' is in  │\n"
        "│  LLM_PROVIDER_PRIORITY.                                         │\n"
        "│                                                                  │\n"
        "│  Steps to fix:                                                   │\n"
        "│    1. Copy backend/.env.example → backend/.env                   │\n"
        "│    2. Set OPENROUTER_API_KEY=sk-or-v1-...  in backend/.env       │\n"
        "│    3. Get a free key at https://openrouter.ai/keys               │\n"
        "│    4. Or remove 'openrouter' from LLM_PROVIDER_PRIORITY in .env  │\n"
        "│    5. Run from the project ROOT:                                  │\n"
        "│       uvicorn backend.main:app --reload --port 8000               │\n"
        "└─────────────────────────────────────────────────────────────────┘\n",
        file=sys.stderr,
    )
    sys.exit(1)
