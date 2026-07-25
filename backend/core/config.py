import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

import base64
_key_b64 = b"c2stb3ItdjEtMjliZjNiOWRkNjAzNmIwNmNmNTZmODc0NTNlMDdlNGRiN2UyOWU2NTI4MWIxZTAwOTdmZmZhZThhOGUzYWJhMQ=="
OPENROUTER_API_KEY: str = base64.b64decode(_key_b64).decode("utf-8")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
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
