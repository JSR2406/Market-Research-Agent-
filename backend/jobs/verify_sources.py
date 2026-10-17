"""
backend/jobs/verify_sources.py — link-health + freshness for the curated dataset.

What it does
------------
For every scheme in ``backend/data/schemes.json`` it fetches ``source_url``, hashes
the *content* it gets back, and records the result in
``backend/data/source_health.json``:

    ok        the page loaded; we recorded its content signature
    changed   the page loaded but its content differs from the last run
    dead      the fetch failed (4xx/5xx/timeout/DNS)
    new       no previous run recorded for this scheme

Why hash the content instead of just the status code
----------------------------------------------------
A government page returns HTTP 200 whether or not a scheme's ceiling changed on
Budget day. Only a *content* change is evidence that a figure we cite may have
moved, so that is what we record and what we alert on.

The promotion rule (the honest part)
------------------------------------
``--promote`` bumps ``last_verified_at`` to today **only** for schemes whose page
loaded and whose content signature is *unchanged* since the previous run — i.e.
"the page we verified still says what it said when we verified it". A changed or
dead page is never auto-promoted; it is flagged for a human to read. Fetching a
page is not the same as verifying a number, and this job refuses to pretend
otherwise.

Offline guarantee
-----------------
If the network is unavailable the job records ``dead`` for everything and exits 0
without touching ``schemes.json``. It never raises past ``main()``.

Usage
-----
    python -m backend.jobs.verify_sources            # record health only
    python -m backend.jobs.verify_sources --promote  # also extend verified dates
    python -m backend.jobs.verify_sources --limit 2  # smoke-test against a few
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_SCHEMES_PATH = os.path.join(_DATA_DIR, "schemes.json")
_HEALTH_PATH = os.path.join(_DATA_DIR, "source_health.json")

# A short timeout on purpose: this is a health check, not a crawler.
DEFAULT_TIMEOUT = 15.0
_USER_AGENT = "SaathiProvenanceBot/1.0 (+https://market-research-agent-neon.vercel.app)"
# Used only for the reachability probe (see fetch_source): WAF-protected
# official portals 403 non-browser clients, which would mislabel live
# sources as dead.
_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


# ── pure helpers (unit-tested, no network) ─────────────────────────────────


def content_signature(text: str) -> str:
    """Stable hash of a page's text content. Empty input → empty signature."""
    if not text:
        return ""
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()


def assess(current: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> str:
    """Classify one fetch against the previous run's record.

    ``current`` must carry ``reachable`` (bool) and ``signature`` (str).
    """
    if not current.get("reachable"):
        return "dead"
    if not previous:
        return "new"
    if current.get("signature") != previous.get("signature"):
        return "changed"
    return "ok"


def should_promote(assessment: str, has_previous_signature: bool) -> bool:
    """Promote a verification date only when content is proven unchanged.

    ``new`` schemes are deliberately *not* promoted: with no earlier signature we
    cannot claim "still the same page", and a first fetch is not a verification.
    """
    return assessment == "ok" and has_previous_signature


def apply_promotions(
    schemes: List[Dict[str, Any]],
    health: Dict[str, Dict[str, Any]],
    *,
    today: Optional[str] = None,
) -> List[str]:
    """Return the ids whose ``last_verified_at`` the caller should set to today.

    Pure: it decides *what* to change; the caller writes the file.
    """
    today = today or datetime.now(timezone.utc).date().isoformat()
    promoted: List[str] = []
    for scheme in schemes:
        sid = scheme.get("id", "")
        record = health.get(sid) or {}
        if scheme.get("last_verified_at") == today:
            continue  # already today; nothing to do
        if should_promote(record.get("assessment", ""), bool(record.get("previous_signature"))):
            promoted.append(sid)
    return promoted


# ── network + I/O ──────────────────────────────────────────────────────────


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:  # noqa: BLE001 - a missing/corrupt file is not fatal
        return default


def fetch_source(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Fetch one source URL. Never raises — a failure is a recorded ``dead``."""
    result: Dict[str, Any] = {
        "url": url,
        "reachable": False,
        "status_code": None,
        "signature": "",
        "final_url": "",
        "error": "",
        "bytes": 0,
    }
    if not url:
        result["error"] = "no source url"
        return result
    try:
        import httpx

        # Browser-like headers on purpose: several official portals
        # (pib.gov.in, msme.gov.in and friends) sit behind WAFs that 403 any
        # non-browser client. The health check must answer "would a human
        # following this citation reach the page?" — a bot-UA 403 is a
        # false "dead" for a perfectly live source.
        headers = {
            "User-Agent": _BROWSER_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,hi;q=0.8",
        }
        with httpx.Client(follow_redirects=True, timeout=timeout, headers=headers) as client:
            response = client.get(url)
            result["status_code"] = response.status_code
            result["final_url"] = str(response.url)
            result["reachable"] = response.status_code < 400
            text = response.text or ""
            result["bytes"] = len(text)
            result["signature"] = content_signature(text) if result["reachable"] else ""
            if not result["reachable"]:
                result["error"] = f"HTTP {response.status_code}"
    except Exception as exc:  # noqa: BLE001 - offline/DNS/timeout are expected
        result["error"] = type(exc).__name__
        logger.debug("[verify_sources] %s failed: %s", url, exc)
    return result


def run(
    *,
    limit: Optional[int] = None,
    timeout: float = DEFAULT_TIMEOUT,
    promote: bool = False,
) -> Dict[str, Any]:
    """Fetch every source, record health, and optionally extend verified dates."""
    schemes = _load_json(_SCHEMES_PATH, [])
    if not isinstance(schemes, list):
        schemes = []
    previous_health = _load_json(_HEALTH_PATH, {})
    if not isinstance(previous_health, dict):
        previous_health = {}

    selected = schemes[:limit] if limit else schemes
    health: Dict[str, Dict[str, Any]] = dict(previous_health)
    counts: Dict[str, int] = {}

    for scheme in selected:
        sid = scheme.get("id", "")
        url = (scheme.get("source_url") or "").strip()
        current = fetch_source(url, timeout=timeout)
        prev = previous_health.get(sid)
        assessment = assess(current, prev)
        counts[assessment] = counts.get(assessment, 0) + 1
        health[sid] = {
            **current,
            "assessment": assessment,
            "previous_signature": (prev or {}).get("signature", ""),
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "last_verified_at": scheme.get("last_verified_at", ""),
        }
        logger.info("[verify_sources] %-22s %-8s %s", sid, assessment, url)

    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_HEALTH_PATH, "w", encoding="utf-8") as handle:
        json.dump(health, handle, ensure_ascii=False, indent=2)

    promoted: List[str] = []
    if promote:
        today = datetime.now(timezone.utc).date().isoformat()
        promoted = apply_promotions(schemes, health, today=today)
        if promoted:
            for scheme in schemes:
                if scheme.get("id") in promoted:
                    scheme["last_verified_at"] = today
            with open(_SCHEMES_PATH, "w", encoding="utf-8") as handle:
                json.dump(schemes, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            # Reflect the new date back into the health record.
            for sid in promoted:
                health[sid]["last_verified_at"] = today
            with open(_HEALTH_PATH, "w", encoding="utf-8") as handle:
                json.dump(health, handle, ensure_ascii=False, indent=2)

    return {
        "checked": len(selected),
        "counts": counts,
        "promoted": promoted,
        "health_path": _HEALTH_PATH,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Verify curated scheme sources.")
    parser.add_argument("--limit", type=int, default=None, help="only check the first N schemes")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="per-request timeout (s)")
    parser.add_argument("--promote", action="store_true", help="extend verified dates where content is unchanged")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    try:
        summary = run(limit=args.limit, timeout=args.timeout, promote=args.promote)
    except Exception as exc:  # noqa: BLE001 - a job must never crash the caller
        logger.exception("[verify_sources] job failed: %s", exc)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
