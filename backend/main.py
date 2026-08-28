import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# config.py will sys.exit(1) immediately if OPENROUTER_API_KEY is missing —
# this surfaces the error before uvicorn finishes starting up.
from backend.core import config  # noqa: F401  (import for side-effect / fail-fast)
from backend.api.ws_market import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Market Research Agent")

# ── CORS ──────────────────────────────────────────────────────────────────────
_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
    "http://localhost:3003,http://localhost:3004,http://localhost:3005",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)


@app.on_event("startup")
async def startup_tasks():
    """
    Startup tasks:
    1. Log confirmed configuration so it's visible in uvicorn output.
    2. (Phase 3) Run session retention cleanup to auto-delete stale sessions.
    """
    logger.info(
        f"Market Research Agent started | model={config.MODEL} | "
        f"origins={ALLOWED_ORIGINS}"
    )

    # Phase 3 hook: session retention cleanup (no-op until memory module exists)
    try:
        from backend.core.memory import cleanup_old_sessions
        deleted = cleanup_old_sessions()
        if deleted:
            logger.info(f"[Memory] Retention cleanup: removed {deleted} expired session(s).")
    except ImportError:
        pass  # memory module not yet present


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": config.MODEL,
        "allowed_origins": ALLOWED_ORIGINS,
    }


# ── Voice endpoints (Phase 6 — purely additive) ───────────────────────────────
from fastapi import File, UploadFile, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel


class SpeakRequest(BaseModel):
    text: str


@app.post("/api/voice/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accept an uploaded audio file, return {"text": "..."}.
    Falls back gracefully — never crashes.
    """
    try:
        from backend.core.voice import speech_to_text
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file.")
        text = await speech_to_text(audio_bytes)
        if not text:
            return {"text": "", "warning": "Could not understand audio — please type instead."}
        return {"text": text}
    except Exception as e:
        logger.error(f"[Voice/transcribe] Unexpected error: {e}")
        return {"text": "", "warning": "Voice unavailable right now — please type instead."}


@app.post("/api/voice/speak")
async def speak(body: SpeakRequest):
    """
    Accept {"text": "..."}, return MP3 audio bytes.
    Falls back gracefully — never crashes.
    """
    try:
        from backend.core.voice import text_to_speech
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="Empty text.")
        audio_bytes = await text_to_speech(body.text)
        if not audio_bytes:
            raise HTTPException(status_code=503, detail="Voice synthesis unavailable right now.")
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Voice/speak] Unexpected error: {e}")
        raise HTTPException(status_code=503, detail="Voice synthesis unavailable right now.")
