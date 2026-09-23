"""
backend/api/voice.py — HTTP endpoints for speech and realtime voice (LiveKit).

STT/TTS (/transcribe, /speak) are REST-based and degrade gracefully.
/livekit-token mints a short-lived LiveKit access token so the browser can join
the voice advisory room the agent worker is listening in on. It never hard-fails
the client: missing credentials or a missing optional dependency return a clear
503 instead of crashing.
"""
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.config import LIVEKIT_ADVISOR_ROOM, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL
from backend.core.voice import speech_to_text, text_to_speech

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str


class LiveKitTokenRequest(BaseModel):
    topic: str = ""  # optional context — not stored, kept for future room scoping


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """
    Accept an uploaded audio file, return {"text": "..."}.
    Falls back gracefully — never crashes.
    """
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file.")
        text = await speech_to_text(audio_bytes)
        if not text:
            return {"text": "", "warning": "Could not understand audio — please type instead."}
        return {"text": text}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Voice/transcribe] Unexpected error: {e}")
        return {"text": "", "warning": "Voice unavailable right now — please type instead."}


@router.post("/speak")
async def speak(body: SpeakRequest):
    """
    Accept {"text": "..."}, return MP3 audio bytes.
    Falls back gracefully — never crashes.
    """
    try:
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


@router.post("/livekit-token")
async def livekit_token(body: LiveKitTokenRequest | None = None):
    """
    Mint a short-lived LiveKit access token for the advisory voice room.

    Returns {"url", "token", "room", "identity"}. The backend/.env must have
    LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET set; `livekit-api`
    must be installed (pip install -r backend/requirements-voice.txt).
    """
    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        logger.warning("[Voice/livekit-token] LiveKit credentials not configured")
        raise HTTPException(
            status_code=503,
            detail="LiveKit is not configured. Add LIVEKIT_URL, LIVEKIT_API_KEY "
                   "and LIVEKIT_API_SECRET to backend/.env.",
        )
    try:
        from livekit import api  # optional dependency
    except ImportError:
        logger.warning("[Voice/livekit-token] 'livekit-api' not installed")
        raise HTTPException(
            status_code=503,
            detail="LiveKit SDK missing. Run: pip install -r backend/requirements-voice.txt",
        )

    identity = f"advisor-{uuid.uuid4().hex[:12]}"
    try:
        token = (
            api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_name("GrameenAI Advisor User")
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=LIVEKIT_ADVISOR_ROOM,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
        )
        jwt = token.to_jwt()
    except Exception as e:
        logger.error(f"[Voice/livekit-token] Failed to mint token: {e}")
        raise HTTPException(status_code=500, detail="Could not mint LiveKit token.")

    return {
        "url": LIVEKIT_URL,
        "token": jwt,
        "room": LIVEKIT_ADVISOR_ROOM,
        "identity": identity,
    }
