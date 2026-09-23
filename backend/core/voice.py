"""
backend/core/voice.py
Phase 6 — Voice I/O module.

speech_to_text():
  Primary:  ElevenLabs Scribe v2 (async via httpx, not the sync SDK, avoids threading issues in
            an async FastAPI app).
  Fallback: SpeechRecognition + Google free STT. If that also fails → return "" (caller shows
            graceful message).

text_to_speech():
  Primary:  ElevenLabs TTS flash v2.5 (streaming via httpx, assembled into bytes).
  Secondary: Hugging Face TTS models (free, no API key required for public models).
  Fallback: pyttsx3 offline TTS (written to a temp WAV, read back, deleted).
            If that also fails → return b"" (caller shows graceful message).

Both functions NEVER raise — they catch all exceptions and return the empty sentinel.
Server-side logs always say which engine was used.
"""
import asyncio
import io
import logging
import os
import tempfile
from io import BytesIO
from typing import Optional

import httpx

from backend.core.config import (
    HF_TTS_MODEL,
    HF_TTS_FALLBACK_MODELS,
)

logger = logging.getLogger(__name__)


def _get_elevenlabs_key() -> str:
    return os.getenv("ELEVENLABS_API_KEY", "") or ""


def _tts_model_candidates() -> list:
    """HF TTS models in priority order, deduplicated."""
    return list(dict.fromkeys([HF_TTS_MODEL, *HF_TTS_FALLBACK_MODELS]))


# ─────────────────────────────────────────────────────────────────────────────
# Speech-to-text
# ─────────────────────────────────────────────────────────────────────────────

async def speech_to_text(audio_bytes: bytes) -> str:
    """
    Transcribe audio bytes to text.
    Returns "" on total failure (never raises).
    """
    key = _get_elevenlabs_key()
    if key:
        result = await _stt_elevenlabs(audio_bytes, key)
        if result:
            logger.info("[Voice/STT] ElevenLabs engine used.")
            return result
        logger.warning("[Voice/STT] ElevenLabs failed, trying SpeechRecognition fallback.")
    else:
        logger.info("[Voice/STT] No ElevenLabs key — using SpeechRecognition fallback directly.")

    result = await _stt_speech_recognition(audio_bytes)
    if result:
        logger.info("[Voice/STT] SpeechRecognition (Google free) engine used.")
        return result

    logger.error("[Voice/STT] Both STT engines failed — returning empty string.")
    return ""


async def _stt_elevenlabs(audio_bytes: bytes, api_key: str) -> str:
    """Call ElevenLabs Scribe v2 via REST (avoids sync SDK threading issues)."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": ("audio.webm", BytesIO(audio_bytes), "audio/webm")}
            data = {
                "model_id": "scribe_v2",
                "tag_audio_events": "false",
                "diarize": "false",
            }
            response = await client.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": api_key},
                files=files,
                data=data,
            )
            if response.status_code == 200:
                return response.json().get("text", "")
            logger.warning(f"[Voice/STT] ElevenLabs HTTP {response.status_code}: {response.text[:200]}")
            return ""
    except Exception as e:
        logger.warning(f"[Voice/STT] ElevenLabs exception: {e}")
        return ""


async def _stt_speech_recognition(audio_bytes: bytes) -> str:
    """
    Use SpeechRecognition + Google free STT. Runs sync call in executor.

    SpeechRecognition only decodes RIFF/WAVE audio. Browsers record WebM/Opus,
    which would fail here without an ffmpeg transcode step — so we guard on the
    container and return "" (caller shows a graceful message) instead of burning
    seconds on a doomed decode.
    """
    if not (audio_bytes.startswith(b"RIFF") and b"WAVE" in audio_bytes[:16]):
        logger.warning(
            "[Voice/STT] SpeechRecognition fallback needs WAV audio "
            "(got non-RIFF/WebM container) — skipping."
        )
        return ""
    try:
        import speech_recognition as sr  # type: ignore

        def _sync_recognize() -> str:
            recognizer = sr.Recognizer()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(audio_bytes)
            try:
                with sr.AudioFile(tmp_path) as source:
                    audio_data = recognizer.record(source)
                return recognizer.recognize_google(audio_data)
            except sr.UnknownValueError:
                return ""
            except sr.RequestError as e:
                logger.warning(f"[Voice/STT] SpeechRecognition API error: {e}")
                return ""
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_recognize)

    except ImportError:
        logger.warning("[Voice/STT] SpeechRecognition not installed.")
        return ""
    except Exception as e:
        logger.warning(f"[Voice/STT] SpeechRecognition exception: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Text-to-speech
# ─────────────────────────────────────────────────────────────────────────────

async def text_to_speech(text: str) -> bytes:
    """
    Convert text to MP3 audio bytes.
    Returns b"" on total failure (never raises).
    """
    if not text.strip():
        return b""

    key = _get_elevenlabs_key()
    if key:
        result = await _tts_elevenlabs(text, key)
        if result:
            logger.info("[Voice/TTS] ElevenLabs engine used.")
            return result
        logger.warning("[Voice/TTS] ElevenLabs failed, trying Hugging Face fallback.")

    result = await _tts_huggingface(text)
    if result:
        logger.info("[Voice/TTS] Hugging Face engine used.")
        return result
    logger.warning("[Voice/TTS] Hugging Face failed, trying pyttsx3 fallback.")

    result = await _tts_pyttsx3(text)
    if result:
        logger.info("[Voice/TTS] pyttsx3 offline engine used.")
        return result

    logger.error("[Voice/TTS] All TTS engines failed — returning empty bytes.")
    return b""


async def _tts_elevenlabs(text: str, api_key: str) -> bytes:
    """Stream ElevenLabs TTS and assemble into bytes."""
    # Truncate to avoid hitting large token cost on advisory text
    truncated = text[:1500]
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            payload = {
                "text": truncated,
                "model_id": "eleven_flash_v2_5",
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            }
            response = await client.post(
                "https://api.elevenlabs.io/v1/text-to-speech/JBFqnCBsd6RMkjVDRZzb",
                headers={
                    "xi-api-key": api_key,
                    "Content-Type": "application/json",
                    "Accept": "audio/mpeg",
                },
                json=payload,
            )
            if response.status_code == 200:
                return response.content
            logger.warning(f"[Voice/TTS] ElevenLabs HTTP {response.status_code}: {response.text[:200]}")
            return b""
    except Exception as e:
        logger.warning(f"[Voice/TTS] ElevenLabs exception: {e}")
        return b""


async def _tts_huggingface(text: str) -> bytes:
    """
    Use Hugging Face Inference API TTS models (free for public models).
    Sends text, expects raw audio bytes back. Never raises.
    """
    token = os.getenv("HF_API_TOKEN", "") or ""
    truncated = text[:1000]
    headers = {"Content-Type": "text/plain"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    for model in _tts_model_candidates():
        if not model:
            continue
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    f"https://api-inference.huggingface.co/models/{model}",
                    headers=headers,
                    content=truncated.encode("utf-8"),
                )
                content_type = response.headers.get("content-type", "")
                if response.status_code == 200 and "audio" in content_type.lower():
                    logger.info(f"[Voice/TTS] Hugging Face model {model} used.")
                    return response.content
                if response.status_code == 503:
                    logger.warning(f"[Voice/TTS] HF {model} is loading — retrying once.")
                    await asyncio.sleep(10)
                    response = await client.post(
                        f"https://api-inference.huggingface.co/models/{model}",
                        headers=headers,
                        content=truncated.encode("utf-8"),
                    )
                    content_type = response.headers.get("content-type", "")
                    if response.status_code == 200 and "audio" in content_type.lower():
                        logger.info(f"[Voice/TTS] Hugging Face model {model} used (after load).")
                        return response.content
                logger.warning(
                    f"[Voice/TTS] HF {model} -> {response.status_code} ({content_type or 'no content-type'})"
                )
        except Exception as e:
            logger.warning(f"[Voice/TTS] HF {model} exception: {e}")
    return b""


async def _tts_pyttsx3(text: str) -> bytes:
    """Use pyttsx3 offline TTS. Saves WAV to temp file, reads back bytes."""
    try:
        import pyttsx3  # type: ignore

        def _sync_tts() -> bytes:
            engine = pyttsx3.init()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                engine.save_to_file(text[:1000], tmp_path)
                engine.runAndWait()
                with open(tmp_path, "rb") as f:
                    return f.read()
            finally:
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_tts)

    except ImportError:
        logger.warning("[Voice/TTS] pyttsx3 not installed.")
        return b""
    except Exception as e:
        logger.warning(f"[Voice/TTS] pyttsx3 exception: {e}")
        return b""
