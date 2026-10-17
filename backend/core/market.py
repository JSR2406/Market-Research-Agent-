"""
backend/core/market.py — live reference data with a strict freshness contract (WS-8).

Three datasets, all served through one shape so the UI never has to guess how
old a number is:

  mandi_price   data.gov.in OGD — Agmarknet daily mandi (wholesale) prices
  pincode       data.gov.in OGD — All-India pincode directory
  ifsc          IFSC directory lookup (free, no key)

The rule this module exists to enforce: **a value and the date it refers to
travel together, and a cached value is never presented as current.** Every
response carries ``as_of`` (the date the data itself refers to), ``lag_days``
(today − as_of, so a stale feed is visible), ``fetched_at`` (when we last read
the upstream) and the ``source_url``.

Offline guarantee: every function answers without a network. With no key, or
when the upstream times out, the answer says so and — if we still hold an
earlier copy — reports that copy with ``stale: true`` and its *true* ``as_of``,
rather than inventing a price. Nothing here is ever computed by a model.
"""
import csv
import io
import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from backend.core.memory import SESSIONS_DIR

logger = logging.getLogger(__name__)

# ── storage ───────────────────────────────────────────────────────────────────
# Same runtime area as analytics/chat: under the gitignored sessions dir, so a
# restart keeps the last known value (served as stale, with its real date).
MARKET_DIR = os.path.join(SESSIONS_DIR, "market")
CACHE_FILE = os.path.join(MARKET_DIR, "cache.json")
MAX_CACHE_ENTRIES = 200

# ── upstreams ─────────────────────────────────────────────────────────────────
OGD_BASE = "https://api.data.gov.in/resource"
RBI_IFSC_URL = "https://www.rbi.org.in/Scripts/IFSCSearch.aspx"

_TIMEOUT_SEC = 8.0
_MAX_RECORDS = 25
_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Dataset registry. `key_field` is the env var that gates the feed; a dataset
# without one (IFSC) works keyless. `ttl_seconds` is how long a fetched copy is
# treated as current; after that it is served as stale until it can be refreshed.
DATASETS: Dict[str, Dict[str, Any]] = {
    "mandi_price": {
        "resource_id": "9ef84268-d588-465a-a308-a864a43d0070",
        "key_env": "DATAGOV_API_KEY",
        "params": ("commodity", "market", "state"),
        "ttl_seconds": 6 * 3600,  # daily feed — refresh a few times a day
        "dated": True,
        "source_name": "data.gov.in — Agmarknet daily mandi prices",
        "source_url": f"{OGD_BASE}/9ef84268-d588-465a-a308-a864a43d0070",
        "official_url": "https://agmarknet.gov.in/",
    },
    "pincode": {
        "resource_id": "5c2f62fe-5afa-4119-a499-fec9d604d604",
        "key_env": "DATAGOV_API_KEY",
        "params": ("pincode",),
        "ttl_seconds": 30 * 24 * 3600,  # essentially static reference data
        "dated": False,
        "source_name": "data.gov.in — All India Pincode Directory",
        "source_url": f"{OGD_BASE}/5c2f62fe-5afa-4119-a499-fec9d604d604",
        "official_url": "https://www.indiapost.gov.in/",
    },
    "ifsc": {
        "resource_id": "",
        "key_env": "",
        "params": ("ifsc",),
        "ttl_seconds": 7 * 24 * 3600,  # branches are added rarely
        "dated": False,
        "source_name": "IFSC directory (Razorpay mirror of the RBI list)",
        "source_url": "https://ifsc.razorpay.com/",
        "official_url": RBI_IFSC_URL,
    },
}

DATASET_IDS = tuple(DATASETS.keys())

DISCLAIMER = {
    "en": (
        "Live reference data is quoted as published by the source on the date shown. "
        "Wholesale prices vary by market and day; always confirm on the official portal."
    ),
    "hi": (
        "लाइव डेटा उसी तारीख़ का है जो स्रोत ने बताई है। मंडी भाव हर बाज़ार और दिन में बदलते हैं — "
        "पक्की जानकारी सरकारी पोर्टल पर ही देखें।"
    ),
}

# Curated, deliberately small vocabulary so "live mandi price" only ever fires
# for a commodity we can actually name in English. No model guesses a query.
COMMODITIES = (
    "onion", "potato", "tomato", "wheat", "paddy", "rice", "maize", "cotton",
    "soyabean", "soybean", "groundnut", "mustard", "gram", "bajra", "jowar",
    "chilli", "banana", "grapes", "apple", "mango", "garlic", "ginger",
    "turmeric", "coriander", "cabbage", "cauliflower", "brinjal", "okra",
    "ladyfinger", "cucumber", "carrot", "peas", "arhar", "moong", "urad",
    "sesamum", "sunflower", "copra", "jute", "rubber", "coffee", "tea",
)

INDIAN_STATES = (
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
)


# ── small deterministic helpers ───────────────────────────────────────────────

def _now(now: Optional[datetime] = None) -> datetime:
    return now or datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _norm_key(text: Any) -> str:
    """Field-name normaliser: the OGD datasets are inconsistent about casing."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _field(record: Dict[str, Any], *names: str) -> str:
    """Case/punctuation-insensitive read of a record field."""
    if not isinstance(record, dict):
        return ""
    wanted = {_norm_key(n) for n in names}
    for key, value in record.items():
        if _norm_key(key) in wanted:
            return "" if value is None else str(value).strip()
    return ""


def _int(value: Any) -> Optional[int]:
    text = re.sub(r"[^0-9.]", "", str(value or ""))
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def parse_date(value: Any) -> Optional[date]:
    """Parse the date formats the government feeds actually use."""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None
    return None


# ── cache ─────────────────────────────────────────────────────────────────────

def cache_key(dataset: str, params: Dict[str, str]) -> str:
    """Stable key for one query, e.g. ``mandi_price|commodity=onion``."""
    parts = [f"{k}={params.get(k, '').strip().lower()}" for k in DATASETS[dataset]["params"]]
    return "|".join([dataset] + sorted(parts))


def _read_cache() -> Dict[str, Any]:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_cache(cache: Dict[str, Any]) -> None:
    try:
        os.makedirs(MARKET_DIR, exist_ok=True)
        if len(cache) > MAX_CACHE_ENTRIES:
            ordered = sorted(
                cache.items(), key=lambda kv: str(kv[1].get("fetched_at", "")), reverse=True
            )[:MAX_CACHE_ENTRIES]
            cache = dict(ordered)
        with open(CACHE_FILE, "w", encoding="utf-8") as handle:
            json.dump(cache, handle, ensure_ascii=False, indent=2)
    except Exception as exc:  # cache is an optimisation, never a hard dependency
        logger.info("[Market] cache write skipped: %s", exc)


def clear_cache() -> None:
    """Drop the on-disk cache (used by tests and by an operator after a fix)."""
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except Exception:
        pass


# ── validation ────────────────────────────────────────────────────────────────

def validate_params(dataset: str, params: Optional[Dict[str, str]]) -> Tuple[Dict[str, str], str]:
    """Return ``(clean_params, error)`` — error is "" when the request is usable."""
    if dataset not in DATASETS:
        return {}, "unknown_dataset"
    spec = DATASETS[dataset]
    raw = params or {}
    clean: Dict[str, str] = {}
    for name in spec["params"]:
        value = str(raw.get(name, "") or "").strip()
        if len(value) > 80:
            value = value[:80]
        clean[name] = value

    if dataset == "pincode":
        if not re.fullmatch(r"\d{6}", clean["pincode"]):
            return clean, "pincode_must_be_6_digits"
    elif dataset == "ifsc":
        if not re.fullmatch(r"[A-Za-z]{4}0[A-Za-z0-9]{6}", clean["ifsc"]):
            return clean, "ifsc_looks_invalid"
        clean["ifsc"] = clean["ifsc"].upper()
    else:  # mandi_price
        if not clean["commodity"]:
            return clean, "commodity_required"
    return clean, ""


def _unavailable(dataset: str, key: str, reason: str, cached: Optional[Dict[str, Any]] = None,
                 lang: str = "en") -> Dict[str, Any]:
    """Honest 'no live data' answer, with a stale copy attached when we have one."""
    spec = DATASETS[dataset]
    base = {
        "dataset": dataset,
        "key": key,
        "available": False,
        "live": False,
        "stale": False,
        "cached": False,
        "as_of": None,
        "as_of_known": False,
        "fetched_at": None,
        "lag_days": None,
        "records": [],
        "count": 0,
        "source_name": spec["source_name"],
        "source_url": spec["source_url"],
        "official_url": spec["official_url"],
        "reason": reason,
        "disclaimer": DISCLAIMER["en"],
    }
    if cached and cached.get("payload"):
        payload = cached["payload"]
        base.update(
            {
                "available": True,
                "stale": True,
                "cached": True,
                "as_of": payload.get("as_of"),
                "as_of_known": bool(payload.get("as_of_known")),
                "fetched_at": cached.get("fetched_at"),
                "lag_days": payload.get("lag_days"),
                "records": payload.get("records", []),
                "count": len(payload.get("records", []) or []),
                "reason": f"showing_last_copy:{reason}",
            }
        )
    base["freshness_label"] = _freshness_label(base, dataset)
    return base


def _freshness_label(payload: Dict[str, Any], dataset: str) -> Dict[str, str]:
    """A one-line, deterministic statement of exactly how fresh this is."""
    if not payload.get("available"):
        return {
            "en": "Live data is not available right now — use the official portal link.",
            "hi": "अभी लाइव डेटा उपलब्ध नहीं है — सरकारी पोर्टल के लिंक से देखें।",
        }
    as_of = payload.get("as_of")
    lag = payload.get("lag_days")
    stale = payload.get("stale")
    fetched = str(payload.get("fetched_at") or "")[:10]

    # How the data's own age reads.
    if as_of:
        if lag is None:
            ref_en, ref_hi = f"as of {as_of}", f"{as_of} तक का"
        elif lag <= 0:
            ref_en, ref_hi = f"as of {as_of} (today)", f"{as_of} (आज का)"
        else:
            days = f"{lag} day{'s' if lag != 1 else ''} old"
            ref_en, ref_hi = f"as of {as_of} ({days})", f"{as_of} तक का ({lag} दिन पुराना)"
    elif payload.get("as_of_known"):
        ref_en = "reference data with no date of its own"
        ref_hi = "संदर्भ डेटा, जिसकी अपनी कोई तारीख़ नहीं होती"
    else:
        ref_en, ref_hi = "the source gave no usable date", "स्रोत ने कोई भरोसेमंद तारीख़ नहीं दी"

    if stale:
        # Never dress an old copy up as current: say it is old *and* say when it
        # was fetched, then state the date the data itself belongs to.
        when_en = f" (fetched {fetched})" if fetched else ""
        when_hi = f" ({fetched} को ली गई)" if fetched else ""
        return {
            "en": f"Not live — showing our last copy{when_en}. It is {ref_en}.",
            "hi": f"लाइव नहीं — हमारी पिछली कॉपी{when_hi}। यह {ref_hi} है।",
        }
    return {"en": f"Live, {ref_en}.", "hi": f"लाइव, {ref_hi}।"}


# ── upstream fetch ────────────────────────────────────────────────────────────

def _fetch_json(url: str, params: Optional[List[Tuple[str, str]]] = None) -> Tuple[bool, Any, str]:
    """One HTTP GET. Returns ``(ok, payload, error_code)``."""
    headers = {"User-Agent": _BROWSER_UA, "Accept": "application/json"}
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=_TIMEOUT_SEC,
                         follow_redirects=True)
    except Exception as exc:
        logger.info("[Market] transport error for %s: %s", url, exc)
        return False, None, "transport_error"
    if resp.status_code != 200:
        return False, None, f"upstream_{resp.status_code}"
    ctype = (resp.headers.get("content-type") or "").lower()
    # Quirk documented by data.gov.in: some datasets return CSV whatever `format` says.
    if "json" in ctype or resp.text.lstrip().startswith(("{", "[")):
        try:
            return True, resp.json(), ""
        except Exception:
            return False, None, "unreadable_upstream"
    try:
        return True, list(csv.DictReader(io.StringIO(resp.text))), ""
    except Exception:
        return False, None, "unreadable_upstream"


def _ogd_filters(params: Dict[str, str], *, title: bool = False) -> List[Tuple[str, str]]:
    """The upstream filter field names are case-sensitive (documented quirk)."""
    out = []
    for name, value in params.items():
        if not value:
            continue
        key = name.title() if title else name
        out.append((f"filters[{key}]", value))
    return out


def _fetch_ogd(dataset: str, params: Dict[str, str]) -> Tuple[bool, List[Dict[str, Any]], str]:
    spec = DATASETS[dataset]
    api_key = os.getenv(spec["key_env"], "")
    if not api_key:
        return False, [], "missing_key"

    def _request(title: bool) -> Tuple[bool, List[Dict[str, Any]], str]:
        query = [
            ("api-key", api_key), ("format", "json"),
            ("limit", str(_MAX_RECORDS)), ("offset", "0"),
        ]
        query += _ogd_filters(params, title=title)
        ok, payload, error = _fetch_json(f"{OGD_BASE}/{spec['resource_id']}", query)
        if not ok:
            return False, [], error
        if isinstance(payload, dict):
            records = payload.get("records")
            records = records if isinstance(records, list) else []
        else:
            records = payload if isinstance(payload, list) else []
        return True, [r for r in records if isinstance(r, dict)], ""

    ok, records, error = _request(title=False)
    # Filter names are case-sensitive upstream. An empty result may simply mean
    # we guessed the case wrong, so try the other spelling before giving up —
    # never guessing a *value*.
    if ok and not records and params.get("commodity"):
        ok2, records2, _ = _request(title=True)
        if ok2 and records2:
            return True, records2, ""
    return ok, records, error


def _fetch_ifsc(ifsc: str) -> Tuple[bool, List[Dict[str, Any]], str]:
    ok, payload, error = _fetch_json(f"https://ifsc.razorpay.com/{ifsc}")
    if not ok:
        # A 404 here means "no such code", which is a real answer, not a failure.
        return (False, [], "not_found") if error == "upstream_404" else (False, [], error)
    return (True, [payload], "") if isinstance(payload, dict) else (True, [], "")


def _normalise(dataset: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for record in records[:_MAX_RECORDS]:
        if dataset == "mandi_price":
            when = parse_date(_field(record, "arrival_date", "date", "price_date"))
            row = {
                "commodity": _field(record, "commodity"),
                "variety": _field(record, "variety"),
                "grade": _field(record, "grade"),
                "market": _field(record, "market"),
                "district": _field(record, "district"),
                "state": _field(record, "state"),
                "min_price": _int(_field(record, "min_price", "minprice")),
                "max_price": _int(_field(record, "max_price", "maxprice")),
                "modal_price": _int(_field(record, "modal_price", "modalprice")),
                "date": when.isoformat() if when else "",
            }
        elif dataset == "pincode":
            row = {
                "pincode": _field(record, "pincode"),
                "office": _field(record, "officename", "office_name"),
                "office_type": _field(record, "officetype", "office_type"),
                "delivery": _field(record, "deliverystatus", "delivery_status"),
                "taluk": _field(record, "taluk"),
                "district": _field(record, "districtname", "district"),
                "state": _field(record, "statename", "state"),
            }
        else:  # ifsc
            row = {
                "ifsc": _field(record, "IFSC", "ifsc"),
                "bank": _field(record, "BANK", "bank"),
                "branch": _field(record, "BRANCH", "branch"),
                "address": _field(record, "ADDRESS", "address"),
                "city": _field(record, "CITY", "city"),
                "state": _field(record, "STATE", "state"),
                "micr": _field(record, "MICR", "micr"),
                "contact": _field(record, "CONTACT", "contact"),
            }
        if any(value not in ("", None) for value in row.values()):
            out.append(row)
    return out


def _as_of(dataset: str, records: List[Dict[str, Any]], spec: Dict[str, Any]) -> Tuple[Optional[str], bool]:
    """The date the data refers to, and whether the source publishes one."""
    if dataset == "mandi_price":
        dates = [parse_date(r.get("date")) for r in records]
        dates = [d for d in dates if d]
        if not dates:
            return None, False
        return max(dates).isoformat(), True
    return None, not spec["dated"]


# ── the one public lookup ─────────────────────────────────────────────────────

def lookup(
    dataset: str,
    params: Optional[Dict[str, str]] = None,
    *,
    now: Optional[datetime] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Resolve one market-data query, with its freshness metadata.

    Never raises. Order of preference: a copy fetched inside the TTL is served as
    live; otherwise the upstream is contacted; if that fails, a previous copy is
    served as ``stale`` with its real date; if there is nothing at all, the
    response says ``available: False`` and why.
    """
    if dataset not in DATASETS:
        return {
            "dataset": dataset,
            "key": "",
            "available": False,
            "live": False,
            "stale": False,
            "cached": False,
            "as_of": None,
            "as_of_known": False,
            "fetched_at": None,
            "lag_days": None,
            "records": [],
            "count": 0,
            "source_name": "",
            "source_url": "",
            "official_url": "",
            "reason": "unknown_dataset",
            "freshness_label": {
                "en": "Unknown dataset.",
                "hi": "अज्ञात डेटासेट।",
            },
            "disclaimer": DISCLAIMER["en"],
        }

    spec = DATASETS[dataset]
    clean, error = validate_params(dataset, params)
    key = cache_key(dataset, clean)
    moment = _now(now)

    if error:
        result = _unavailable(dataset, key, error)
        result["freshness_label"] = {
            "en": "Please check what you entered and try again.",
            "hi": "जो लिखा है उसे जाँचकर दोबारा कोशिश करें।",
        }
        return result

    cache = _read_cache()
    entry = cache.get(key)

    # 1. A copy inside its TTL is current.
    if entry and not force:
        fetched = _parse_iso(entry.get("fetched_at"))
        age = (moment - fetched).total_seconds() if fetched else None
        if age is not None and age <= spec["ttl_seconds"]:
            payload = dict(entry.get("payload") or {})
            records = payload.get("records") or []
            payload.update(
                dataset=dataset, key=key, available=True, live=True, stale=False, cached=True,
                records=records, count=len(records),
                source_name=spec["source_name"], source_url=spec["source_url"],
                official_url=spec["official_url"],
                reason="" if records else "no_records",
                disclaimer=DISCLAIMER["en"],
            )
            payload["freshness_label"] = _freshness_label(payload, dataset)
            return payload

    # 2. Talk to the upstream.
    if dataset == "ifsc":
        ok, records, error = _fetch_ifsc(clean["ifsc"])
    else:
        ok, records, error = _fetch_ogd(dataset, clean)

    if not ok:
        return _unavailable(dataset, key, error, cached=entry)

    normalised = _normalise(dataset, records)
    as_of, as_of_known = _as_of(dataset, normalised, spec)
    lag_days: Optional[int] = None
    if as_of:
        try:
            lag_days = (moment.date() - date.fromisoformat(as_of)).days
        except ValueError:
            lag_days = None

    payload = {
        "dataset": dataset,
        "key": key,
        "available": True,
        "live": True,
        "stale": False,
        "cached": False,
        "as_of": as_of,
        "as_of_known": as_of_known,
        "fetched_at": _iso(moment),
        "lag_days": lag_days,
        "records": normalised,
        "count": len(normalised),
        "source_name": spec["source_name"],
        "source_url": spec["source_url"],
        "official_url": spec["official_url"],
        "reason": "" if normalised else "no_records",
        "disclaimer": DISCLAIMER["en"],
    }
    payload["freshness_label"] = _freshness_label(payload, dataset)

    cache[key] = {
        "fetched_at": payload["fetched_at"],
        "payload": {k: payload[k] for k in ("as_of", "as_of_known", "lag_days", "records")},
    }
    _write_cache(cache)
    return payload


def _parse_iso(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ── query extraction for the research pipeline ────────────────────────────────

def extract_query(topic: str, intake: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """
    Deterministically read a commodity/state out of the user's own words.

    Only English commodity names and full state names are recognised — when the
    words do not match we return nothing and no live figure is quoted, rather
    than asking a model to guess what the user grows. The commodity is returned
    in its canonical display form (``"Onion"``), since the upstream filters are
    case-sensitive.
    """
    haystack = f"{topic or ''} {' '.join((intake or {}).values())}".lower()
    commodity = ""
    for candidate in COMMODITIES:
        # Accept the everyday plural too ("onions", "tomatoes").
        if re.search(rf"\b{re.escape(candidate)}(?:s|es)?\b", haystack):
            commodity = candidate.title()
            break
    state = next((s for s in INDIAN_STATES if s.lower() in haystack), "")

    market = ""
    text = topic or ""
    name = r"([A-Za-z][A-Za-z .'-]{2,40})"
    # Prefer "<place> mandi" ("at the Lasalgaon mandi"), since the trailing word
    # is the reliable signal; fall back to "mandi at <place>" / "market in X".
    match = re.search(rf"\b(?:at|in)\s+(?:the\s+)?{name}\s+(?:mandi|market)\b", text, re.IGNORECASE)
    if not match:
        match = re.search(rf"\b(?:mandi|market)\s+(?:at|in)\s+{name}", text, re.IGNORECASE)
    if match:
        market = match.group(1).strip().rstrip(".,;")
    return {"commodity": commodity, "market": market, "state": state}


def live_context(topic: str, intake: Optional[Dict[str, str]] = None) -> str:
    """
    A labelled block for the research prompt when a live figure is genuinely
    available, else "". Deterministic: it quotes the fetched record verbatim and
    says exactly when it is from, so the writer can prefer it over a web claim.
    """
    query = extract_query(topic, intake)
    if not query["commodity"]:
        return ""
    try:
        result = lookup("mandi_price", query)
    except Exception as exc:  # never break a research run over a market feed
        logger.info("[Market] live context lookup failed: %s", exc)
        return ""
    if not result.get("available") or not result.get("records"):
        return ""

    lines = [
        f"Live mandi price (source: {result['source_name']}, {result['source_url']}):",
        f"Freshness: {result['freshness_label']['en']}",
    ]
    for row in result["records"][:5]:
        if row.get("modal_price") is None:
            continue
        where = " / ".join(p for p in (row.get("market"), row.get("district"), row.get("state")) if p)
        lines.append(
            f"- {row.get('commodity', query['commodity']).title()}"
            f"{f' ({row['variety']})' if row.get('variety') else ''}"
            f" modal Rs {row['modal_price']}"
            f" (min {row.get('min_price')}, max {row.get('max_price')})"
            f"{f' at {where}' if where else ''}"
            f"{f' on {row.get('date')}' if row.get('date') else ''}"
        )
    if len(lines) <= 2:
        return ""
    lines.append(
        "Prefer this over a web-search estimate; if quoting it, label it "
        f"\"live, as of {result.get('as_of') or 'the date shown'}\"."
    )
    return "\n".join(lines)


# ── status ────────────────────────────────────────────────────────────────────

def status(*, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Which feeds are configured and what we hold — cheap, no network."""
    cache = _read_cache()
    datasets = []
    for dataset, spec in DATASETS.items():
        configured = True if not spec["key_env"] else bool(os.getenv(spec["key_env"], ""))
        held = [v for k, v in cache.items() if str(k).startswith(f"{dataset}|")]
        latest = max((str(v.get("fetched_at", "")) for v in held), default="")
        datasets.append(
            {
                "id": dataset,
                "configured": configured,
                "key_env": spec["key_env"],
                "ttl_seconds": spec["ttl_seconds"],
                "dated": spec["dated"],
                "source_name": spec["source_name"],
                "source_url": spec["source_url"],
                "official_url": spec["official_url"],
                "cached_queries": len(held),
                "last_fetched_at": latest,
            }
        )
    return {"datasets": datasets, "disclaimer": DISCLAIMER["en"],
            "server_time": _iso(_now(now))}
