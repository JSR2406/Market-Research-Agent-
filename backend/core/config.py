import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.getenv(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
)
# Free tier via OpenRouter — Nemotron
MODEL: str = os.getenv(
    "MODEL", "nvidia/nemotron-3-super-120b-a12b:free"
)

if not OPENROUTER_API_KEY:
    import warnings
    warnings.warn(
        "OPENROUTER_API_KEY is not set. All LLM calls will fail with 401. "
        "Set it in your .env file or deployment environment variables.",
        stacklevel=2,
    )
