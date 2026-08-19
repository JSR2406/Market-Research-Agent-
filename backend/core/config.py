import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# Configured LLM model with fallbacks
MODEL: str = os.getenv("LLM_MODEL", "meta-llama/llama-3.3-70b-instruct")

# Priority fallback models if primary model is unavailable or encounters API errors
FALLBACK_MODELS: list[str] = [
    MODEL,
    "google/gemini-2.5-flash",
    "meta-llama/llama-3.3-70b-instruct",
    "google/gemma-2-9b-it:free",
    "meta-llama/llama-3-8b-instruct:free",
    "mistralai/mistral-7b-instruct:free",
    "openrouter/auto",
    "openrouter/free",
]

if not OPENROUTER_API_KEY:
    import warnings
    warnings.warn(
        "OPENROUTER_API_KEY is not set. All LLM calls will fail with 401. "
        "Set it in your .env file or deployment environment variables.",
        stacklevel=2,
    )
