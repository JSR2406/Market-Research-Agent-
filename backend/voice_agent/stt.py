"""
stt.py — open-source streaming STT for the LiveKit voice worker.

Wraps the project's local faster-whisper model (no API key, handles Hindi)
as a LiveKit ``stt.STT`` plugin. Audio frames are buffered per utterance and
transcribed when the session flushes (VAD end-of-speech), so no cloud STT key
is ever required.

Targets livekit-agents==1.8.x (see backend/requirements-voice.txt).
"""
from __future__ import annotations

import asyncio
import io
import logging
import wave

import numpy as np
from livekit import rtc
from livekit.agents import stt
from livekit.agents.utils import AudioBuffer

logger = logging.getLogger("backend.voice_agent.stt")

_TARGET_RATE = 16000


def _resample_mono(frame: rtc.AudioFrame) -> np.ndarray:
    """Remix to mono float32 and resample to 16 kHz via linear interpolation."""
    data = np.frombuffer(frame.data, dtype=np.int16).astype(np.float32)
    channels = frame.num_channels or 1
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if frame.sample_rate == _TARGET_RATE:
        return data
    ratio = _TARGET_RATE / float(frame.sample_rate)
    out_len = max(1, int(round(len(data) * ratio)))
    old_idx = np.linspace(0, len(data) - 1, num=out_len)
    return np.interp(old_idx, np.arange(len(data)), data).astype(np.float32)


def _pcm_to_wav_bytes(pcm: np.ndarray) -> bytes:
    pcm16 = np.clip(pcm, -32768, 32767).astype(np.int16).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_TARGET_RATE)
        w.writeframes(pcm16)
    return buf.getvalue()


class FasterWhisperSTT(stt.STT):
    """Buffered faster-whisper STT: transcribes on flush, emits final transcripts."""

    def __init__(self) -> None:
        super().__init__(capabilities=stt.STTCapabilities(streaming=True, interim_results=False))
        self._model = None
        self._model_lock = asyncio.Lock()

    async def _ensure_model(self):  # shared singleton with backend/core/voice.py
        if self._model is not None:
            return self._model
        async with self._model_lock:
            if self._model is not None:
                return self._model
            from faster_whisper import WhisperModel  # type: ignore

            from backend.core.voice import WHISPER_MODEL_SIZE

            loop = asyncio.get_event_loop()
            self._model = await loop.run_in_executor(
                None, lambda: WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
            )
            logger.info(f"[Voice/STT] faster-whisper '{WHISPER_MODEL_SIZE}' loaded for LiveKit.")
            return self._model

    async def _transcribe_pcm(self, pcm: np.ndarray) -> str:
        if pcm.size < _TARGET_RATE // 2:  # < 0.5s of audio — likely noise
            return ""
        model = await self._ensure_model()
        wav_bytes = _pcm_to_wav_bytes(pcm)

        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(wav_bytes)
        try:
            loop = asyncio.get_event_loop()

            def _run() -> str:
                segments, _info = model.transcribe(tmp_path, beam_size=1)
                return "".join(seg.text for seg in segments).strip()

            return await loop.run_in_executor(None, _run)
        finally:
            import os

            try:
                os.remove(tmp_path)
            except OSError:
                pass

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: str | None = None,
        conn_options=None,
    ) -> stt.SpeechEvent:
        pcm = np.frombuffer(buffer.data, dtype=np.int16).astype(np.float32)
        text = await self._transcribe_pcm(pcm)
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=language or "en", text=text)],
        )

    def stream(self, *, language: str | None = None, conn_options=None) -> stt.RecognizeStream:
        return _BufferedStream(self, language=language)


class _BufferedStream(stt.RecognizeStream):
    """Accumulates frames; transcribes the utterance when the session flushes."""

    def __init__(self, stt_plugin: FasterWhisperSTT, *, language: str | None) -> None:
        super().__init__()
        self._plugin = stt_plugin
        self._language = language or "en"
        self._chunks: list[np.ndarray] = []

    async def _run(self) -> None:
        try:
            async for msg in self._input_ch:
                if isinstance(msg, self._FlushSentinel):
                    await self._flush_utterance()
                elif isinstance(msg, rtc.AudioFrame):
                    self._chunks.append(_resample_mono(msg))
        except Exception as e:
            logger.warning(f"[Voice/STT] recognize stream ended: {e}")

    async def _flush_utterance(self) -> None:
        if not self._chunks:
            return
        pcm = np.concatenate(self._chunks)
        self._chunks.clear()
        try:
            text = await self._plugin._transcribe_pcm(pcm)
        except Exception as e:
            logger.warning(f"[Voice/STT] transcription failed: {e}")
            return
        if not text:
            return
        self._event_ch.send_nowait(
            stt.SpeechEvent(
                type=stt.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt.SpeechData(language=self._language, text=text)],
            )
        )
        self._event_ch.send_nowait(
            stt.SpeechEvent(type=stt.SpeechEventType.END_OF_SPEECH)
        )
