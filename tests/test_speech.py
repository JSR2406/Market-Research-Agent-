"""
tests/test_speech.py — browser-native voice (WS-9).

The promise this pins is narrow and worth keeping: on the browser voice path
audio is never uploaded. ``frontend/lib/speech.ts`` uses only the device's own
SpeechRecognition / speechSynthesis, so it must contain no ``fetch`` call and no
API base URL at all — if someone ever adds one, this test fails, because the
privacy chip in the UI would then be lying.

The second pinned point is the fallback: the server STT/TTS endpoints must still
be wired wherever the device cannot do it, or voice dies on browsers without the
Web Speech API.
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SPEECH = FRONTEND / "lib" / "speech.ts"
I18N = FRONTEND / "lib" / "i18n.tsx"
TOPIC_INPUT = FRONTEND / "components" / "TopicInput.tsx"
ADVISORY = FRONTEND / "components" / "AdvisoryCard.tsx"
CHAT = FRONTEND / "components" / "ChatPanel.tsx"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dictionary(source: str, name: str) -> dict:
    match = re.search(rf"const {name}: Record<string, string> = \{{(.*?)\n\}};", source, re.DOTALL)
    assert match, f"{name} dictionary not found in i18n.tsx"
    return dict(re.findall(r'^\s*"([^"]+)":\s*"(.*)",\s*$', match.group(1), re.MULTILINE))


# ── the device path never touches the network ─────────────────────────────────


def test_speech_module_exists():
    assert SPEECH.exists(), "frontend/lib/speech.ts is where the browser voice path lives"


def test_the_device_voice_path_uploads_nothing():
    source = _read(SPEECH)
    assert "fetch(" not in source, "the on-device path must never upload audio or text"
    assert "API_BASE" not in source, "the on-device path must not know a backend URL"
    assert "XMLHttpRequest" not in source
    assert "FormData" not in source


def test_speech_module_uses_the_browser_apis():
    source = _read(SPEECH)
    assert "speechSynthesis" in source          # text → speech, on the device
    assert "SpeechRecognition" in source        # speech → text, on the device
    assert "webkitSpeechRecognition" in source  # Safari/older Chrome spelling
    assert "SpeechSynthesisUtterance" in source


def test_speech_degrades_quietly_without_the_apis():
    source = _read(SPEECH)
    # Both entry points return null rather than throwing when unsupported.
    assert "return null" in source
    assert "typeof window" in source            # SSR-safe: no `window` at import time


# ── the spoken reply follows the site language ────────────────────────────────


def test_the_speech_language_follows_the_site_locale():
    source = _read(SPEECH)
    assert 'locale === "hi"' in source
    assert "hi-IN" in source, "a Hindi page must be spoken (and heard) in Hindi"
    assert "en-IN" in source


# ── listening and speaking are wired, with the server as fallback ─────────────


@pytest.mark.parametrize("path", [TOPIC_INPUT, ADVISORY, CHAT])
def test_the_device_path_is_wired_into_the_ui(path):
    assert "from \"@/lib/speech\"" in _read(path), f"{path.name} must use the shared speech layer"


def test_topic_input_prefers_the_device_and_keeps_the_server_recorder():
    source = _read(TOPIC_INPUT)
    assert "startListening(" in source
    assert "speechSupport()" in source
    # The old upload path stays for browsers without Web Speech.
    assert "/api/voice/transcribe" in source


def test_advisory_listen_prefers_the_device_and_keeps_the_server_voice():
    source = _read(ADVISORY)
    assert "speak(" in source
    assert "speechSupport().synthesis" in source
    assert "/api/voice/speak" in source


def test_chat_has_voice_input():
    source = _read(CHAT)
    assert "startListening(" in source
    assert "Mic" in source and "MicOff" in source


def test_microphone_permission_denied_is_explained_not_swallowed():
    # A blocked mic must say so, in words a user can act on.
    assert "not-allowed" in _read(TOPIC_INPUT)
    assert "not-allowed" in _read(CHAT)


# ── the new copy exists in both languages ─────────────────────────────────────


@pytest.fixture(scope="module")
def dictionaries():
    source = _read(I18N)
    return _dictionary(source, "EN"), _dictionary(source, "HI")


@pytest.mark.parametrize(
    "key",
    [
        "voice.device",
        "listen.start",
        "listen.loading",
        "listen.stop",
        "listen.error",
        "listen.playbackFailed",
        "chat.mic",
        "chat.micStop",
        "chat.listening",
        "chat.micDenied",
        "chat.micUnheard",
    ],
)
def test_voice_keys_are_translated_in_both_languages(dictionaries, key):
    en, hi = dictionaries
    assert key in en, f"{key} missing from the English dictionary"
    assert key in hi, f"{key} missing from the Hindi dictionary"
    assert en[key].strip() and hi[key].strip()


def test_the_voice_copy_states_the_privacy_promise(dictionaries):
    en, _hi = dictionaries
    assert "nothing is uploaded" in en["voice.device"].lower()
