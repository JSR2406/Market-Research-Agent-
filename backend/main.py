import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# config.py exits immediately if OPENROUTER_API_KEY is missing while "openrouter"
# is in the provider priority — this surfaces the error before uvicorn starts.
from backend.core import config  # noqa: F401  (import for side-effect / fail-fast)
from backend.api.voice import router as voice_router
from backend.api.chat import router as chat_router
from backend.api.sessions import router as sessions_router
from backend.api.ws_market import router as ws_router
from backend.core.memory import cleanup_old_sessions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ── CORS ──────────────────────────────────────────────────────────────────────
_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
    "http://localhost:3003,http://localhost:3004,http://localhost:3005",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw.split(",") if o.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Market Research Agent started | model={config.MODEL} | "
        f"origins={ALLOWED_ORIGINS}"
    )
    # Session retention cleanup: auto-delete stale sessions older than 7 days.
    try:
        deleted = cleanup_old_sessions()
        if deleted:
            logger.info(f"[Memory] Retention cleanup: removed {deleted} expired session(s).")
    except Exception as e:
        logger.error(f"[Memory] Retention cleanup failed: {e}")
    yield


app = FastAPI(title="Market Research Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(voice_router)
app.include_router(chat_router)
app.include_router(sessions_router)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": config.MODEL,
        "allowed_origins": ALLOWED_ORIGINS,
    }