"""
tests/test_i18n.py — the site-wide language layer.

Two things can silently break the language feature, so they are pinned here:
a key that exists in English but not in Hindi (users would see English text
mid-page), and a language leaking into a place it should not (official scheme
names and amounts must stay in English, or users cannot match them to a bank
form).
"""
import json
import re
from pathlib import Path

import pytest

I18N = Path(__file__).resolve().parents[1] / "frontend" / "lib" / "i18n.tsx"
SCHEMES = Path(__file__).resolve().parents[1] / "backend" / "data" / "schemes.json"


def _parse_dictionary(source: str, name: str) -> dict:
    """Pull one `const <NAME>: Record<string, string> = { ... };` block."""
    match = re.search(rf"const {name}: Record<string, string> = \{{(.*?)\n\}};", source, re.DOTALL)
    assert match, f"{name} dictionary not found in i18n.tsx"
    body = match.group(1)
    return dict(re.findall(r'^\s*"([^"]+)":\s*"(.*)",\s*$', body, re.MULTILINE))


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def dictionaries():
    source = I18N.read_text(encoding="utf-8")
    return _parse_dictionary(source, "EN"), _parse_dictionary(source, "HI")


def test_english_dictionary_is_substantial(dictionaries):
    en, _ = dictionaries
    assert len(en) > 120, f"only {len(en)} keys — the site is not fully wired up"


def test_every_english_key_has_a_hindi_translation(dictionaries):
    """
    A missing key silently renders English mid-Hindi page, which looks broken
    to the user. This is the single most valuable test in the i18n layer.
    """
    en, hi = dictionaries
    missing = sorted(set(en) - set(hi))
    assert not missing, f"no Hindi translation for: {missing}"


def test_no_orphan_hindi_keys(dictionaries):
    """Catches keys renamed in English but left behind in Hindi."""
    en, hi = dictionaries
    orphans = sorted(set(hi) - set(en))
    assert not orphans, f"Hindi keys with no English source: {orphans}"


def test_placeholders_match_between_languages(dictionaries):
    """A dropped {name} renders a sentence with a hole in it."""
    en, hi = dictionaries
    for key, template in hi.items():
        expected = set(re.findall(r"\{(\w+)\}", en.get(key, "")))
        actual = set(re.findall(r"\{(\w+)\}", template))
        assert actual == expected, f"{key}: Hindi placeholders {actual} != English {expected}"


def test_offical_terms_stay_in_english_in_hindi(dictionaries):
    """
    Users must recognise Udyam / MUDRA / GST / PM SVANidhi on a bank form, so
    these are deliberately never translated — only the sentence around them is.
    """
    en, hi = dictionaries
    english_blob = " ".join(en.values())
    hindi_blob = " ".join(hi.values())
    for term in ("Udyam", "MUDRA", "PMEGP", "CGTMSE", "GST", "PM SVANidhi", "ElevenLabs"):
        if term not in english_blob:
            continue  # not used in the English copy either
        assert term in hindi_blob, f"official term {term} is missing from the Hindi copy"


def test_every_scheme_check_has_a_hindi_label():
    """
    Rule labels are shown on every not-eligible card, so leaving them English
    would make the verdict panel half-translated.
    """
    schemes = json.loads(SCHEMES.read_text(encoding="utf-8"))
    missing = []
    for scheme in schemes:
        for check in scheme.get("checks") or []:
            if not check.get("label_hi"):
                missing.append(f"{scheme['id']}/{check.get('id')}")
    assert not missing, f"scheme checks without a Hindi label: {missing}"


def test_hindi_copy_is_actually_devanagari(dictionaries):
    """Guards against a placeholder 'hi' dictionary that silently copies English."""
    _, hi = dictionaries
    for key in ("quiz.title", "input.start", "ledger.title", "elig.title"):
        value = hi.get(key, "")
        assert value, f"{key} missing"
        assert any("\u0900" <= ch <= "\u097F" for ch in value), f"{key} is not in Devanagari: {value}"


def test_hindi_input_classifies_correctly():
    """
    The classifier matches on Devanagari terms a Hindi user actually types
    ("ठेला", "रेहड़ी", "मुरली", "गाय"). Corrupted regexes silently degrade to
    `other`, which would then make every eligibility verdict guess "likely".
    """
    from backend.core.business import (
        AGRICULTURE_ALLIED,
        HOME_BASED,
        STREET_VENDING,
        classify_business,
    )

    cases = [
        ("ठेला लगाता हूँ", STREET_VENDING),
        ("मैं रेहड़ी पर फल बेचता हूँ", STREET_VENDING),
        ("घर पर मुरली बनाती हूँ", HOME_BASED),
        ("मेरे पास 8 गायें हैं, दूध बेचता हूँ", AGRICULTURE_ALLIED),
        ("दुकान पर कपड़े बेचता हूँ", "trading"),
    ]
    for text, expected in cases:
        assert classify_business({"business": text})["primary"] == expected, text


def test_business_label_follows_language_but_class_does_not():
    from backend.core.business import classify_business

    en = classify_business({"business": "Farm / dairy"}, "", "en")
    hi = classify_business({"business": "Farm / dairy"}, "", "hi")
    assert en["primary"] == hi["primary"], "language must not change the verdict"
    assert en["label"] != hi["label"], "the user-facing label must be translated"
    assert "à¤" not in hi["label"]


def test_no_source_file_is_mojibake():
    """
    Guards a real bug: a PowerShell round-trip once re-encoded
    `business.py`'s Hindi as UTF-8 bytes read through latin-1, shipping
    "à¤¡à¥‡à¤¯à¤°" to the browser instead of "डेयरी". Nothing else catches it —
    the file still parses and the tests still pass.
    """
    root = Path(__file__).resolve().parents[1]
    suspects = [
        root / "backend" / "core" / "business.py",
        root / "backend" / "core" / "intake.py",
        root / "backend" / "core" / "eligibility.py",
        root / "backend" / "core" / "benefits.py",
        root / "backend" / "core" / "documents.py",
        root / "frontend" / "lib" / "i18n.tsx",
        root / "frontend" / "lib" / "intake.ts",
        root / "frontend" / "components" / "StartupQuiz.tsx",
        SCHEMES,
    ]
    for path in suspects:
        text = path.read_text(encoding="utf-8")
        assert "�" not in text, f"{path.name} contains replacement characters"
        # 'à¤' is the signature of UTF-8 Devanagari decoded through latin-1.
        assert "à¤" not in text, f"{path.name} looks mojibake (UTF-8 read as latin-1)"


def test_hindi_labels_reach_the_api_unmangled(client):
    """End-to-end: the Devanagari must survive normalize → classify → JSON."""
    r = client.post(
        "/api/eligibility",
        json={"intake": {"business": "Farm / dairy"}, "lang": "hi"},
    )
    assert r.status_code == 200
    body = r.json()
    for value in (body["business_label"], body["questions"]["business"]):
        assert "à" not in value, f"mojibake in API response: {value!r}"
        assert any("\u0900" <= ch <= "\u097F" for ch in value), value
    assert body["business_label"] != "unspecified business"


def test_ws_lang_is_validated_server_side():
    """An unvalidated client `lang` would be interpolated straight into a prompt."""
    from backend.api.ws_market import VALID_LANGS, _as_lang

    assert _as_lang("hi") == "hi"
    assert _as_lang("HI") == "hi"
    assert _as_lang("en") == "en"
    # Anything unexpected falls back rather than reaching an LLM prompt.
    for bad in (None, 123, "fr", "hi; drop table", ["hi"], {"a": 1}, ""):
        assert _as_lang(bad) == "en", f"{bad!r} should fall back to English"
    assert set(VALID_LANGS) == {"en", "hi"}