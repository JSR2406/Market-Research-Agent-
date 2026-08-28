import os
import sys
from dotenv import load_dotenv

# Always load from backend/.env relative to this file's location
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_API_KEY_2: str = os.getenv("OPENROUTER_API_KEY_2", "")  # optional second key for rate-limit rotation
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Configured LLM model with fallbacks
MODEL: str = os.getenv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")

# Priority fallback models if primary model is unavailable or encounters API errors.
# NOTE: :free models are rate-limited quickly on shared quota — keep this list short
# and only include models verified to be available. Update when a model goes 404.
FALLBACK_MODELS: list[str] = [
    MODEL,
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "meta-llama/llama-3.3-70b-instruct:free",
    "qwen/qwen-2.5-coder-32b-instruct:free",
    "google/gemini-2.0-flash-lite-preview-02-05:free",
    "openrouter/auto",
    "openrouter/free",
]

# ── Fail-fast guard ────────────────────────────────────────────────────────────
# A missing API key causes silent 401s deep in workflows. Surface the error
# immediately at import time so uvicorn exits with a clear message instead of
# starting up in a permanently broken state.
#
# Skip the check during pytest / test runs so existing test scripts that patch
# the key after import can still load the module.
_in_test = "pytest" in sys.modules or os.getenv("PYTEST_RUNNING") == "1"

if not OPENROUTER_API_KEY and not _in_test:
    print(
        "\n"
        "┌─────────────────────────────────────────────────────────────────┐\n"
        "│  FATAL: OPENROUTER_API_KEY is not set.                         │\n"
        "│                                                                  │\n"
        "│  Steps to fix:                                                   │\n"
        "│    1. Copy backend/.env.example → backend/.env                   │\n"
        "│    2. Set OPENROUTER_API_KEY=sk-or-v1-...  in backend/.env       │\n"
        "│    3. Get a free key at https://openrouter.ai/keys               │\n"
        "│    4. Run from the project ROOT:                                  │\n"
        "│       uvicorn backend.main:app --reload --port 8000               │\n"
        "└─────────────────────────────────────────────────────────────────┘\n",
        file=sys.stderr,
    )
    sys.exit(1)
