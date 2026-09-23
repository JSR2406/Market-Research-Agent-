"""
backend/api/voice.py — HTTP endpoints for speech-to-text and text-to-speech.

Both endpoints are purely additive and degrade gracefully: they never hard-fail
the client, they always surface a human-readable message instead.
"""
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from backend.core.voice import speech_to_text, text_to_speech

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str


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