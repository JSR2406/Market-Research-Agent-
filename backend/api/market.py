"""
backend/api/market.py — live reference data endpoints (WS-8).

  GET /api/market         one lookup, with its freshness metadata
  GET /api/market/status  which feeds are configured / what we hold (no network)

These are read-only lookups of published reference data. The point of the
endpoint shape is honesty about age: every answer carries ``as_of`` (the date the
data refers to), ``lag_days`` and ``fetched_at``, and a lagging feed is returned
as ``stale`` with its true date rather than being dressed up as current.

Nothing here needs a database, and every path answers with no network: with no
``DATAGOV_API_KEY`` (or when an upstream is unreachable) the response says so and
links the official portal instead of inventing a price.
"""
import logging

from fastapi import APIRouter, Query

from backend.api.schemas import (
    MarketDatasetInfo,
    MarketResponse,
    MarketStatusResponse,
)
from backend.core.market import (
    DISCLAIMER,
    lookup,
    status as market_status,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["market"])

_LANGS = {"en", "hi"}

# Deterministic, human explanations for each machine-readable reason code.
_REASON_TEXT = {
    "missing_key": {
        "en": "Live data is not switched on for this feed yet. Use the official portal link below.",
        "hi": "इस फ़ीड के लिए लाइव जानकारी अभी चालू नहीं है। नीचे दिए सरकारी पोर्टल के लिंक पर देखें।",
    },
    "transport_error": {
        "en": "The live source could not be reached just now. Please try again in a few minutes.",
        "hi": "अभी लाइव स्रोत तक नहीं पहुँच पाए। कुछ मिनट बाद दोबारा कोशिश करें।",
    },
    "not_found": {
        "en": "No record found for that code. Please check it and try again.",
        "hi": "इस कोड का कोई रिकॉर्ड नहीं मिला। कोड जाँचकर दोबारा कोशिश करें।",
    },
    "pincode_must_be_6_digits": {
        "en": "A pincode has 6 digits — please check what you typed.",
        "hi": "पिनकोड 6 अंकों का होता है — जो लिखा है उसे जाँचें।",
    },
    "ifsc_looks_invalid": {
        "en": "An IFSC code is 11 characters, like HDFC0001234.",
        "hi": "IFSC कोड 11 अक्षरों का होता है, जैसे HDFC0001234।",
    },
    "commodity_required": {
        "en": "Please name the crop or commodity you want a price for.",
        "hi": "जिस फ़सल या चीज़ का भाव चाहिए, उसका नाम लिखें।",
    },
    "unknown_dataset": {
        "en": "That dataset is not available.",
        "hi": "वह डेटासेट उपलब्ध नहीं है।",
    },
}


def _lang(value: str) -> str:
    return value if value in _LANGS else "en"


def _reason_text(reason: str, lang: str) -> str:
    text = _REASON_TEXT.get(reason)
    if not text:
        return ""
    return text.get(lang) or text["en"]


@router.get("/market", response_model=MarketResponse)
async def get_market(
    dataset: str = Query("mandi_price", max_length=32),
    key: str = Query("", max_length=80),
    commodity: str = Query("", max_length=80),
    market: str = Query("", max_length=80),
    state: str = Query("", max_length=80),
    pincode: str = Query("", max_length=12),
    ifsc: str = Query("", max_length=16),
    lang: str = Query("en", max_length=8),
):
    """
    Resolve one live-data query.

    ``dataset`` is one of ``mandi_price`` (commodity [+ market/state]),
    ``pincode`` (6 digits) or ``ifsc`` (11 characters). ``key`` is accepted as a
    shorthand for the dataset's primary field. The response always says how old
    the data is; when the feed is unavailable it says that too.
    """
    language = _lang(lang)
    # `key` is the documented shorthand: the dataset's one essential value.
    if dataset == "pincode":
        pincode = pincode or key
    elif dataset == "ifsc":
        ifsc = ifsc or key
    else:
        commodity = commodity or key

    params = {
        "commodity": commodity,
        "market": market,
        "state": state,
        "pincode": pincode,
        "ifsc": ifsc,
    }
    result = lookup(dataset, params)
    label = result.get("freshness_label") or {}

    return MarketResponse(
        dataset=result.get("dataset", dataset),
        key=result.get("key", ""),
        available=bool(result.get("available")),
        live=bool(result.get("live")),
        stale=bool(result.get("stale")),
        cached=bool(result.get("cached")),
        as_of=result.get("as_of"),
        as_of_known=bool(result.get("as_of_known")),
        fetched_at=result.get("fetched_at"),
        lag_days=result.get("lag_days"),
        records=result.get("records") or [],
        count=result.get("count", 0),
        source_name=result.get("source_name", ""),
        source_url=result.get("source_url", ""),
        official_url=result.get("official_url", ""),
        reason=result.get("reason", ""),
        note=label.get(language) or label.get("en") or "",
        error="" if result.get("available") else _reason_text(result.get("reason", ""), language),
        disclaimer=DISCLAIMER[language],
    )


@router.get("/market/status", response_model=MarketStatusResponse)
async def get_market_status(lang: str = Query("en", max_length=8)):
    """Which feeds exist, whether each is configured, and what we hold locally."""
    info = market_status()
    return MarketStatusResponse(
        datasets=[MarketDatasetInfo(**row) for row in info.get("datasets", [])],
        disclaimer=DISCLAIMER[_lang(lang)],
        server_time=info.get("server_time", ""),
    )
