"""
business.py — deterministic classification of what kind of business this is.

The eligibility engine needs a *stable business class*, not keywords. A user's
own words ("I make and sell goat milk soap from my home") have to land on a
class that matches what the schemes actually say about it.

Classification order matters and is deliberate. The most specific signals win,
and product-making signals are tested **before** agriculture so that someone
who sells goat-milk soap is not mistaken for a dairy farmer. Single animal
words are only an allied-agriculture signal when no crop signal is present.

Every class is deterministic: same words in, same class out. No LLM is involved
— the model's job is to explain the verdict, never to decide it.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Stable class ids. These strings appear in schemes.json `checks[].values`, so
# renaming one means updating the dataset too.
AGRICULTURE_CROP = "agriculture_crop"
AGRICULTURE_ALLIED = "agriculture_allied"
MANUFACTURING = "manufacturing"
HOME_BASED = "home_based"
STREET_VENDING = "street_vending"
TRADING = "trading"
SERVICES = "services"
OTHER = "other"

BUSINESS_CLASSES: Tuple[str, ...] = (
    AGRICULTURE_CROP,
    AGRICULTURE_ALLIED,
    MANUFACTURING,
    HOME_BASED,
    STREET_VENDING,
    TRADING,
    SERVICES,
    OTHER,
)

CLASS_LABELS: Dict[str, str] = {
    AGRICULTURE_CROP: "crop cultivation",
    AGRICULTURE_ALLIED: "allied agriculture (dairy / poultry / beekeeping)",
    MANUFACTURING: "manufacturing",
    HOME_BASED: "home-based production",
    STREET_VENDING: "street vending",
    TRADING: "shop / retail trading",
    SERVICES: "services",
    OTHER: "unspecified business",
}

# Hindi + English + common transliterations. Signals are matched against the
# intake answers and the free-text topic.
_STREET_RE = re.compile(
    r"street\s*(vendor|vending|cart)|\bcart\b|\bthela\b|hawker|pavement|"
    r"mobile\s*cart|door\s*to\s*door|ठेला|ठेले|रेहड़ी|पटरी|फेरी|चलता|घुमणे",
    re.IGNORECASE,
)
_HOME_RE = re.compile(
    r"home[- ]?based|home\s*business|from\s*(my|our)?\s*home|work\s*from\s*home|"
    r"in\s*my\s*kitchen|\bkitchen\b|"
    r"किचन|घर\s*(पर|में)|अपने\s*घर|आँगन|आंगन",
    re.IGNORECASE,
)
_MAKE_RE = re.compile(
    r"\bmak(e|ing)\b|manufactur|\bproduce\b|\bprocess\b|bakery|papad|pickle|"
    r"soap|candle|garment|curry|khadi|handicraft|handloom|footwear|jewell|"
    r"furniture|cooker|मुरली|साबुन|बनाना|निर्माण|उत्पादन|कपड़ा|अचार|पापड़|"
    r" tailoring\s*(work|stitch)|stitching",
    re.IGNORECASE,
)
_CROP_RE = re.compile(
    r"cultivat|\bcrop\b|\bcrops\b|\bfarming\b|\bwheat\b|\brice\b|paddy|maize|"
    r"\bcotton\b|sugarcane|mustard|soybean|\bvegetable|\borchard|fruit\s*farm|"
    r"grow\w*\s+(vegetable|fruit|rice|wheat|crop|flower|plant|seed)|"
    r"फसल|खेती|बोई|गेहूँ|गेहूं|धान|कृषि| खेत",
    re.IGNORECASE,
)
_ALLIED_RE = re.compile(
    r"\bdairy\b|\bmilk\b|\bcow\b|\bcows\b|cattle|buffalo|\bgoat\b|\bpoultry\b|"
    r"\bchicken\b|\begg?s?\b|honey|beekeep|apiary|\bfish\b|prawn|sericulture|"
    r"poultry|दुग्ध|दुग्ध\s*व्यवसाय|पशु|गाय|बकरी|मुर्गी|अंडा|मधुमक्खी|मछली",
    re.IGNORECASE,
)
_SERVICE_RE = re.compile(
    r"\bservice\b|repair|technician|plumb|electrician|\btuition\b|coaching|"
    r"salon|barber|beauty|\btransport\b|driver|deliver(y|ies)?\bservice|"
    r"photograph|event\s*manage|tailor|सेवा|मरम्मत|ट्यूशन|स्कूल|व्यापार|"
    r"मैकेनिक|ब्यूटी",
    re.IGNORECASE,
)
_TRADE_RE = re.compile(
    r"\bshop\b|\bstore\b|retail|kirana|dukan|\bmarket\b|wholesale|supplier|"
    r"boutique|\boutlet\b|दुकान|किराना|दुकानदार|थोक",
    re.IGNORECASE,
)

# Chip labels the frontend stores verbatim, mapped straight to a class. These
# are exact matches on what the user actually picked, so they outrank free text.
_CHIP_CLASS: Dict[str, str] = {
    "street vendor / cart": STREET_VENDING,
    "shop / stall": TRADING,
    "home-based / freelance": HOME_BASED,
    "service / repair": SERVICES,
    "farm / dairy": AGRICULTURE_ALLIED,  # refined by text below if it is crops
}


def _matches(pattern: re.Pattern, *texts: str) -> bool:
    return any(pattern.search(t) for t in texts if t)


def classify_business(
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
) -> Dict[str, object]:
    """
    Return ``{"primary", "secondary", "signals", "label"}`` for one business.

    ``signals`` lists the literal matched words so a verdict can explain *why*
    it classified that way — an unexplained verdict is not trustworthy advice.
    """
    answers = intake or {}
    business = str(answers.get("business") or "").strip()
    offering = str(answers.get("offering") or "").strip()
    texts = tuple(t for t in (business, offering, topic) if t)

    signals: List[str] = []
    secondary: List[str] = []

    # 1. An exact chip the user picked is the strongest evidence available.
    chip = _CHIP_CLASS.get(business.lower())
    if chip:
        signals.append(f"picked “{business}”")

    # 2. Street vending is unambiguous — a cart is a cart.
    if _matches(_STREET_RE, *texts) or chip == STREET_VENDING:
        if chip and chip != STREET_VENDING:
            secondary.append(chip)
        signals.append("street vending")
        return _result(STREET_VENDING, secondary, signals)

    # 3. Making things at home — tested BEFORE agriculture so "goat milk soap
    #    from my home" is production, not dairy farming.
    makes = _matches(_MAKE_RE, *texts)
    at_home = _matches(_HOME_RE, *texts) or chip == HOME_BASED
    if (makes and at_home) or (at_home and not _matches(_ALLIED_RE, *texts)):
        signals.append("home-based production")
        if makes:
            signals.append("makes its own goods")
        extra = [MANUFACTURING] if makes else []
        return _result(HOME_BASED, secondary + extra, signals)
    if makes:
        signals.append("manufactures its own goods")
        return _result(MANUFACTURING, secondary, signals)

    # 4. Agriculture: crops beat allied-animal signals when both are present.
    has_crop = _matches(_CROP_RE, *texts)
    has_allied = _matches(_ALLIED_RE, *texts)
    if has_crop:
        signals.append("crop cultivation")
        if has_allied:
            signals.append("also mentions livestock")
        extra = [AGRICULTURE_ALLIED] if has_allied else []
        return _result(AGRICULTURE_CROP, secondary + extra, signals)
    if has_allied or chip == AGRICULTURE_ALLIED:
        signals.append("allied agriculture")
        return _result(AGRICULTURE_ALLIED, secondary, signals)

    # 5. Everything else.
    if _matches(_SERVICE_RE, *texts) or chip == SERVICES:
        signals.append("service business")
        return _result(SERVICES, secondary, signals)
    if _matches(_TRADE_RE, *texts) or chip == TRADING:
        signals.append("shop / retail trade")
        return _result(TRADING, secondary, signals)

    return _result(OTHER, secondary, signals)


def _result(primary: str, secondary: List[str], signals: List[str]) -> Dict[str, object]:
    return {
        "primary": primary,
        "secondary": [c for c in dict.fromkeys(secondary) if c and c != primary],
        "signals": [s for s in dict.fromkeys(signals) if s],
        "label": CLASS_LABELS.get(primary, primary),
    }


def is_known(primary: str) -> bool:
    """False for the `other` bucket — callers must not treat it as a verdict."""
    return primary in BUSINESS_CLASSES and primary != OTHER