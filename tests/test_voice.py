"""
Voice layer evaluation: open-source no-key engine ladder, diagnostics contract,
and HTTP caps/guards. All tests are offline — every network/engine call is
mocked, so the suite never starts models or downloads piper voices.

Covers:
- /api/voice/status contract (typed, stable, no engine startup)
- TTS ladder order + first-success-wins isolation (piper → HF → pyttsx3)
- Piper voice auto-selection (Devanagari → Hindi voice)
- /speak media-type sniffing (WAV from piper vs MP3 from cloud tiers)
- transcribe/speak input guards (empty, oversized)

Run from repo root:  .venv\\Scripts\\python.exe -m pytest tests/test_voice.py -q
"""
import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.core import voice as voice_core


# ── unit: ladder & engine internals (never touches the network) ─────────────

def test_tts_ladder_uses_piper_first_when_no_key(monkeypatch):
    """With no key, the open-source local engines are tried in order and the
    function still returns the empty sentinel when every tier fails."""

    async def _boom_missing(text):
        return b""

    called = []
    monkeypatch.setattr(voice_core, "_get_elevenlabs_key", lambda: "")

    async def _fake_piper(text):
        called.append("piper")
        return b""

    async def _fake_hf(text):
        called.append("huggingface")
        return b""

    async def _fake_pyttsx3(text):
        called.append("pyttsx3")
        return b""

    monkeypatch.setattr(voice_core, "_tts_piper", _fake_piper)
    monkeypatch.setattr(voice_core, "_tts_huggingface", _fake_hf)
    monkeypatch.setattr(voice_core, "_tts_pyttsx3", _fake_pyttsx3)

    result = asyncio.run(voice_core.text_to_speech("hello"))
    assert result == b""
    assert called == ["piper", "huggingface", "pyttsx3"]


def test_tts_ladder_stops_at_first_success(monkeypatch):
    """A successful open-source tier short-circuits — later tiers are never reached."""

    called = []
    monkeypatch.setattr(voice_core, "_get_elevenlabs_key", lambda: "")

    async def _ok_piper(text):
        called.append("piper")
        return b"RIFF-WAVE-data"

    async def _should_not_run(text):
        called.append("leak")
        return b""

    monkeypatch.setattr(voice_core, "_tts_piper", _ok_piper)
    monkeypatch.setattr(voice_core, "_tts_huggingface", _should_not_run)
    monkeypatch.setattr(voice_core, "_tts_pyttsx3", _should_not_run)

    result = asyncio.run(voice_core.text_to_speech("hello"))
    assert result == b"RIFF-WAVE-data"
    assert called == ["piper"]


def test_piper_voice_selection_by_script(monkeypatch):
    """Devanagari text selects the Hindi voice, Latin/English selects the English one."""
    asked = []

    async def _fake_load(name):
        asked.append(name)
        return None  # model missing → no synthesis, b"" sentinel, never raises

    monkeypatch.setattr(voice_core, "_load_piper_voice", _fake_load)

    assert asyncio.run(voice_core._tts_piper("नमस्ते मेरा व्यापार")) == b""
    assert asked == [voice_core.PIPER_VOICE_HI]

    assert asyncio.run(voice_core._tts_piper("my shop sells vegetables")) == b""
    assert asked == [voice_core.PIPER_VOICE_HI, voice_core.PIPER_VOICE_EN]


def test_piper_missing_package_never_raises(monkeypatch):
    monkeypatch.setattr(voice_core, "_importable", lambda _m: False)
    # _load_piper_voice short-circuits on missing package; _tts_piper returns b"".
    assert asyncio.run(voice_core._tts_piper("hello")) == b""


def test_voice_status_is_typed_and_stable():
    status = voice_core.voice_status()
    assert status["stt_default"] in ("elevenlabs", "faster_whisper", "speech_recognition", "none")
    assert status["tts_default"] in ("elevenlabs", "piper", "huggingface", "pyttsx3", "none")
    assert set(status["stt_engines"]) == {"elevenlabs", "faster_whisper", "speech_recognition"}
    assert set(status["tts_engines"]) == {"elevenlabs", "piper", "huggingface", "pyttsx3"}
    assert isinstance(status["private_by_default"], bool)
    # Kernel engine availability is a deterministic reflection of install state.
    assert status["stt_engines"]["faster_whisper"] is True
    assert status["tts_engines"]["piper"] is True
    assert set(status["piper_voices"]) == {"en", "hi"}


# ── HTTP surface ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client():
    from backend.main import app

    with TestClient(app) as c:
        yield c


def test_voice_status_endpoint_contract(client):
    r = client.get("/api/voice/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "whisper_model", "stt_engines", "tts_engines",
        "stt_default", "tts_default", "piper_voices", "private_by_default",
    }
    assert body["whisper_model"] in ("tiny", "base", "small")


def test_speak_sniffs_wav_for_piper_bytes(client, monkeypatch):
    """Piper returns RIFF/WAV; the endpoint must label it audio/wav, not audio/mpeg."""

    async def _fake_wav(text):
        return b"RIFF\x00\x00\x00\x00WAVEfmt "

    async def _fake_mp3(text):
        return b"\xff\xfb" + b"ID3-audio"

    monkeypatch.setattr("backend.api.voice.text_to_speech", _fake_wav)
    r = client.post("/api/voice/speak", json={"text": "hello shopkeeper"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/wav")
    assert r.content.startswith(b"RIFF")

    monkeypatch.setattr("backend.api.voice.text_to_speech", _fake_mp3)
    r = client.post("/api/voice/speak", json={"text": "hello shopkeeper"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")


def test_speak_rejects_empty_text(client):
    r = client.post("/api/voice/speak", json={"text": "   "})
    assert r.status_code == 400


def test_transcribe_rejects_empty_upload(client):
    r = client.post("/api/voice/transcribe", files={"file": ("empty.webm", b"", "audio/webm")})
    assert r.status_code == 400
    assert "audio" in r.json()["detail"].lower()


def test_transcribe_rejects_oversized_upload(client):
    payload = b"x" * (5 * 1024 * 1024 + 1)
    r = client.post(
        "/api/voice/transcribe", files={"file": ("big.webm", payload, "audio/webm")}
    )
    assert r.status_code == 413
    # Friendly generic message — no internals leaked.
    detail = r.json()["detail"]
    assert isinstance(detail, str) and len(detail) < 200


def test_transcribe_graceful_warning_when_no_text(client, monkeypatch):
    """Total STT failure surfaces as 200 {text:"", warning} so the UI can react."""

    async def _no_speech(audio_bytes):
        return ""

    monkeypatch.setattr("backend.api.voice.speech_to_text", _no_speech)
    r = client.post("/api/voice/transcribe", files={"file": ("a.webm", b"RIFF-audio", "audio/webm")})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == ""
    assert "understand" in body["warning"]