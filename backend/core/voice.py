"""
backend/core/voice.py
Phase 6 — Voice I/O module. Private-by-default: when no API key is configured,
every engine used here is open-source and runs locally (or via free public
endpoints) — nothing sends microphone audio to a third party.

speech_to_text():
  Primary:  ElevenLabs Scribe v2 (async via httpx, not the sync SDK, avoids threading issues in
            an async FastAPI app). Used only when ELEVENLABS_API_KEY is set.
  Default (no key): faster-whisper (fully open-source, local, no API key; handles WebM/Opus
            directly and supports Hindi). Model size via WHISPER_MODEL_SIZE (default "tiny").
  Fallback: SpeechRecognition + Google free STT (WAV only). If all fail → return ""
            (caller shows graceful message).

text_to_speech():
  Primary:  ElevenLabs TTS flash v2.5 (streaming via httpx, assembled into bytes).
            Used only when ELEVENLABS_API_KEY is set.
  Default (no key): Piper TTS (MIT, local ONNX, fully offline after a one-time
            model download; auto-switches English/Hindi via Devanagari detection).
  Fallback: Hugging Face TTS models (free, no API key required for public models).
  Fallback: pyttsx3 offline TTS (written to a temp WAV, read back, deleted).
            If that also fails → return b"" (caller shows graceful message).

Both functions NEVER raise — they catch all exceptions and return the empty sentinel.
Server-side logs always say which engine was used. voice_status() reports engine
availability for operators / the frontend privacy chip.
"""
import asyncio
import importlib.util
import io
import logging
import os
import tempfile
import threading
import wave
from io import BytesIO
from typing import Optional

import httpx

from backend.core.config import (
    HF_TTS_MODEL,
    HF_TTS_FALLBACK_MODELS,
    PIPER_VOICE_DIR,
    PIPER_VOICE_EN,
    PIPER_VOICE_HI,
)

logger = logging.getLogger(__name__)

# Open-source local STT model size: "tiny" (75 MB, fastest) | "base" | "small".
# Overridable via WHISPER_MODEL_SIZE in backend/.env. Downloaded once from
# Hugging Face on first use, then cached locally.
WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "tiny")

# Lazily-loaded faster-whisper singleton (kept module-level so the model
# weights load once per process, not once per request).
_whisper_model = None

# ── Piper TTS (open-source, local, no API key) ────────────────────────────────
# Models live under PIPER_VOICE_DIR; singletons cache loaded PiperVoice objects.
# _piper_lock guards download + load so concurrent first calls don't race.
_piper_models_dir = PIPER_VOICE_DIR
_piper_voices: dict = {}
_piper_lock = threading.Lock()

# Naming convention ex: gridder en_US-les-sac-medium → hi_IN-pratham-medium.
_PIPER_VOICES_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def _importable(module: str) -> bool:
    """Cheap spec probe — no import side-effects (used by voice_status())."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _is_devanagari(text: str) -> bool:
    """True when the text contains Devanagari script (Hindi) — selects the hi voice."""
    return any("\u0900" <= ch <= "\u097F" for ch in text)


def _piper_voice_url(voice_name: str, ext: str = ".onnx") -> str:
    """Resolve the canonical HF folder layout for a piper voice name."""
    lang_code, speaker, quality = voice_name.split("-", 2)
    language = lang_code.split("_")[0]
    return (
        f"{_PIPER_VOICES_BASE}/{language}/{lang_code}/{speaker}/{quality}/"
        f"{voice_name}{ext}"
    )


def _download_piper_voice_file(voice_name: str, path: str) -> None:
    """Download one piper file (.onnx or .onnx.json). Raises on any failure."""
    ext = ".onnx.json" if path.endswith(".onnx.json") else ".onnx"
    url = _piper_voice_url(voice_name, ext)
    with httpx.Client(timeout=300.0, follow_redirects=True) as client:
        resp = client.get(url)
        if resp.status_code != 200:
            raise RuntimeError(f"[Voice/TTS] piper download failed HTTP {resp.status_code} for {url}")
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(resp.content)
        os.replace(tmp, path)


def _load_piper_sync(voice_name: str):
    """
    Download (once) + load a PiperVoice singleton. Runs inside a worker thread.
    Returns the voice object or None (never raises).
    """
    with _piper_lock:
        if voice_name in _piper_voices:
            return _piper_voices[voice_name]
        try:
            os.makedirs(_piper_models_dir, exist_ok=True)
            base = os.path.join(_piper_models_dir, voice_name)
            for suffix in (".onnx", ".onnx.json"):
                path = base + suffix
                if not (os.path.isfile(path) and os.path.getsize(path) > 0):
                    _download_piper_voice_file(voice_name, path)
            from piper import PiperVoice  # type: ignore  # noqa: F401 — optional dep

            voice = PiperVoice.load(base + ".onnx")
            _piper_voices[voice_name] = voice
            logger.info(f"[Voice/TTS] piper voice '{voice_name}' ready.")
            return voice
        except Exception as e:
            logger.warning(f"[Voice/TTS] piper voice '{voice_name}' unavailable: {e}")
            _piper_voices[voice_name] = None
            return None


async def _load_piper_voice(voice_name: str):
    """Async wrapper — heavy download/load stays off the event loop."""
    if voice_name in _piper_voices and _piper_voices[voice_name] is not None:
        return _piper_voices[voice_name]
    if not _importable("piper"):
        logger.warning("[Voice/TTS] piper package not installed.")
        return None
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _load_piper_sync, voice_name)


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
        logger.warning("[Voice/STT] ElevenLabs failed, trying faster-whisper fallback.")
    else:
        logger.info("[Voice/STT] No ElevenLabs key — using faster-whisper fallback directly.")

    result = await _stt_faster_whisper(audio_bytes)
    if result:
        logger.info("[Voice/STT] faster-whisper (open-source local) engine used.")
        return result

    result = await _stt_speech_recognition(audio_bytes)
    if result:
        logger.info("[Voice/STT] SpeechRecognition (Google free) engine used.")
        return result

    logger.error("[Voice/STT] All STT engines failed — returning empty string.")
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


async def _stt_faster_whisper(audio_bytes: bytes) -> str:
    """
    Fully open-source local STT via faster-whisper (CTranslate2, CPU-friendly).

    Handles WebM/Opus browser recordings directly (no ffmpeg transcode step),
    auto-detects language (English/Hindi/…). Model downloads once on first use.
    Runs the blocking inference in an executor. Never raises.
    """
    if not audio_bytes:
        return ""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError:
        logger.warning("[Voice/STT] faster-whisper not installed.")
        return ""
    try:
        # Compat shim: faster-whisper passes metadata_errors="ignore" to av.open(),
        # but PyAV >= 15 removed that kwarg (and av<15 has no Python 3.14 Windows
        # wheel). Dropping the kwarg restores default open behaviour.
        try:
            import av as _av  # type: ignore

            if not getattr(_av.open, "__grameen_patched__", False):
                _orig_open = _av.open

                def _patched_open(*args: object, **kwargs: object) -> object:
                    kwargs.pop("metadata_errors", None)
                    return _orig_open(*args, **kwargs)

                _patched_open.__grameen_patched__ = True  # type: ignore[attr-defined]
                _av.open = _patched_open  # type: ignore[assignment]
        except Exception as e:
            logger.warning(f"[Voice/STT] av compat shim failed (continuing anyway): {e}")

        global _whisper_model
        if _whisper_model is None:
            def _load() -> object:
                return WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")

            loop = asyncio.get_event_loop()
            _whisper_model = await loop.run_in_executor(None, _load)
            logger.info(f"[Voice/STT] faster-whisper model '{WHISPER_MODEL_SIZE}' loaded.")

        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(audio_bytes)
        try:
            def _transcribe() -> str:
                segments, _info = _whisper_model.transcribe(tmp_path, beam_size=1)
                return "".join(seg.text for seg in segments).strip()

            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _transcribe)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    except Exception as e:
        logger.warning(f"[Voice/STT] faster-whisper exception: {e}")
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
    Convert text to audio bytes.
    Returns b"" on total failure (never raises).

    Engine ladder (first success wins):
      1. ElevenLabs        — only when ELEVENLABS_API_KEY is set (cloud, best quality)
      2. Piper TTS        — open-source, local, no API key (offline after warm-up)
      3. Hugging Face     — free public TTS models (network, no key)
      4. pyttsx3          — offline device TTS (robotic, last resort)

    The output container varies by engine (MP3 vs WAV); callers that need a
    hard media type sniff the bytes before responding.
    """
    if not text.strip():
        return b""

    key = _get_elevenlabs_key()
    if key:
        result = await _tts_elevenlabs(text, key)
        if result:
            logger.info("[Voice/TTS] ElevenLabs engine used.")
            return result
        logger.warning("[Voice/TTS] ElevenLabs failed, trying piper fallback.")
    else:
        logger.info("[Voice/TTS] No ElevenLabs key — open-source piper engine first.")

    result = await _tts_piper(text)
    if result:
        logger.info("[Voice/TTS] piper (open-source local) engine used.")
        return result
    logger.warning("[Voice/TTS] piper failed, trying Hugging Face fallback.")

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


async def _tts_piper(text: str) -> bytes:
    """
    Fully open-source, local, no-key TTS via Piper (MIT, ONNX). Auto-selects a
    voice by script: Devanagari text → Hindi voice, otherwise English. Returns
    the synthesized bytes (RIFF/WAV) or b"" — never raises.
    """
    try:
        voice_name = PIPER_VOICE_HI if _is_devanagari(text) else PIPER_VOICE_EN
        voice = await _load_piper_voice(voice_name)
        if voice is None:
            return b""
        truncated = text[:1000]

        def _synth() -> bytes:
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wav:
                voice.synthesize_wav(truncated, wav)
            return buf.getvalue()

        loop = asyncio.get_event_loop()
        audio = await loop.run_in_executor(None, _synth)
        if audio:
            logger.info(f"[Voice/TTS] piper voice '{voice_name}' synthesized {len(audio)} bytes.")
        return audio
    except Exception as e:
        logger.warning(f"[Voice/TTS] piper exception: {e}")
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


# ─────────────────────────────────────────────────────────────────────────────
# Engine diagnostics (drives GET /api/voice/status and the frontend privacy chip)
# ─────────────────────────────────────────────────────────────────────────────

def voice_status() -> dict:
    """
    Report which STT/TTS engines are available in this deployment and which the
    ladder defaults to. Availability is a cheap spec probe (no engine startup),
    so this endpoint is always fast and never triggers model downloads.
    """
    has_key = bool(_get_elevenlabs_key())

    stt_map = {
        "elevenlabs": has_key,
        "faster_whisper": _importable("faster_whisper"),
        "speech_recognition": _importable("speech_recognition"),
    }
    tts_map = {
        "elevenlabs": has_key,
        "piper": _importable("piper"),
        "huggingface": True,  # httpx + public HF Inference API — no key, always eligible
        "pyttsx3": _importable("pyttsx3"),
    }

    stt_order = ["elevenlabs", "faster_whisper", "speech_recognition"]
    tts_order = ["elevenlabs", "piper", "huggingface", "pyttsx3"]

    return {
        "whisper_model": WHISPER_MODEL_SIZE,
        "stt_engines": stt_map,
        "tts_engines": tts_map,
        "stt_default": next((k for k in stt_order if stt_map[k]), "none"),
        "tts_default": next((k for k in tts_order if tts_map[k]), "none"),
        "piper_voices": {"en": PIPER_VOICE_EN, "hi": PIPER_VOICE_HI},
        "private_by_default": not has_key,  # no key → every engine is local/free
    }
