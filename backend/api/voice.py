"""
backend/api/voice.py — HTTP endpoints for speech, realtime voice (LiveKit) and
engine diagnostics.

STT/TTS (/transcribe, /speak) are REST-based and degrade gracefully and are
private-by-default: with no API key they run on open-source local engines
(faster-whisper STT, Piper TTS). /status reports which engines are available so
the frontend can show an honest "voice runs locally" chip and operators can
diagnose the deployment. /livekit-token mints a short-lived LiveKit access token
so the browser can join the voice advisory room the agent worker is listening in
on. It never hard-fails the client: missing credentials or a missing optional
dependency return a clear 503 instead of crashing.
"""
import logging
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from backend.api.schemas import (
    LiveKitTokenRequest,
    LiveKitTokenResponse,
    SpeakRequest,
    TranscribeResponse,
    VoiceStatusResponse,
)
from backend.core.config import LIVEKIT_ADVISOR_ROOM, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL
from backend.core.voice import speech_to_text, text_to_speech, voice_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])

MAX_AUDIO_BYTES = 5 * 1024 * 1024  # 5 MB — reject oversized uploads early


@router.get("/status", response_model=VoiceStatusResponse)
async def voice_status_endpoint() -> dict:
    """
    Engine diagnostics: which STT/TTS engines are available and the active
    defaults. Cheap (spec probes only) — does not start models or download.
    """
    return voice_status()


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    """
    Accept an uploaded audio file, return {"text": "..."}.
    Falls back gracefully — never crashes.
    """
    try:
        audio_bytes = await file.read(MAX_AUDIO_BYTES + 1)
        if len(audio_bytes) > MAX_AUDIO_BYTES:
            raise HTTPException(status_code=413, detail="Audio file too large (max 5 MB).")
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
Accept {"text": "..."}, return audio bytes (MP3 or WAV by engine).
    Falls back gracefully — never crashes.
    """
    try:
        if not body.text.strip():
            raise HTTPException(status_code=400, detail="Empty text.")
        audio_bytes = await text_to_speech(body.text)
        if not audio_bytes:
            raise HTTPException(status_code=503, detail="Voice synthesis unavailable right now.")
        # The open-source Piper tier returns RIFF/WAV while cloud tiers return MP3 —
        # sniff the container so the browser always gets the right media type.
        media_type = (
            "audio/wav"
            if audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]
            else "audio/mpeg"
        )
        return Response(content=audio_bytes, media_type=media_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Voice/speak] Unexpected error: {e}")
        raise HTTPException(status_code=503, detail="Voice synthesis unavailable right now.")


@router.post("/livekit-token", response_model=LiveKitTokenResponse)
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
            .with_name("Business Saathi User")
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
