"""
analytics.py — first-party, aggregate-only product analytics.

Why this is hand-rolled instead of a tracker
--------------------------------------------
The product's privacy promise is that there are no third-party scripts and no
personal data leaves the user's session. A funnel is still useful — "how many
people who started a check-up actually ran a research?" — so this module records
*counts of named events* and nothing else.

Hard rules, enforced in code (not by convention):

* **Allowlist only.** An event whose name is not in ``EVENT_ALLOWLIST`` is dropped,
  never stored. Renaming a button cannot leak a free-text string into analytics.
* **No free text, no PII.** Only a tiny set of scalar property keys survive
  sanitisation; anything else is discarded. Property values are type-checked and
  length-capped.
* **No identifiers except the anonymous session id.** A session id that fails the
  shared allowlist is dropped — analytics must never become a way around the
  session-id guard.
* **Local files, short retention.** Daily JSONL under ``sessions/analytics/``
  (gitignored, pruned after ``RETENTION_DAYS``). No network, ever — so the
  offline guarantee holds.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

from backend.core.memory import SESSIONS_DIR, is_valid_session_id

logger = logging.getLogger(__name__)

ANALYTICS_DIR = os.path.join(SESSIONS_DIR, "analytics")

# The complete vocabulary of events the app may record. Adding an event means
# adding it here on purpose — there is no wildcard.
EVENT_ALLOWLIST = frozenset(
    {
        "page_view",
        "checkup_start",
        "checkup_complete",
        "research_start",
        "research_done",
        "research_cancel",
        "scheme_view",
        "eligibility_view",
        "ledger_tick",
        "export_session",
        "delete_session",
        "chat_message",
        "voice_use",
        "advisory_download",
        "tracker_scheme_added",
        "tracker_alerts_saved",
        "market_view",
    }
)

# Property keys that may be stored, with the scalar type each must be. Anything
# not listed is dropped. Deliberately tiny: enough to slice a funnel, not enough
# to reconstruct what anyone typed.
PROP_SCHEMA: Dict[str, type] = {
    "page": str,
    "lang": str,
    "status": str,
    "engine": str,
    "count": int,
    "score": int,
    "step": str,
    "source": str,
    "dataset": str,
    "scheme": str,
    "channel": str,
}

_MAX_PROPS = len(PROP_SCHEMA)
_MAX_STRING = 40
_MAX_EVENTS_PER_BATCH = 50
_MAX_NAME = 40

# The ordered funnel the dashboard reports. Each label is what the API shows.
FUNNEL_STEPS = ("checkup_start", "checkup_complete", "research_start", "research_done")

RETENTION_DAYS = 30


def _today(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).date().isoformat()


def _daily_path(day: str) -> str:
    return os.path.join(ANALYTICS_DIR, f"{day}.jsonl")


def _clean_value(value: Any) -> Optional[Any]:
    if isinstance(value, bool):  # bool is an int subclass — keep it out of counts
        return None
    if isinstance(value, int):
        return max(-1_000_000, min(1_000_000, value))
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        return text[:_MAX_STRING] if text else None
    return None


def sanitize_event(event: Any) -> Optional[Dict[str, Any]]:
    """Return a storable version of one event, or ``None`` to drop it.

    This is the only door into storage. If it does not match the schema exactly,
    it does not get written.
    """
    if not isinstance(event, dict):
        return None
    name = event.get("name")
    if not isinstance(name, str):
        return None
    name = name.strip()[:_MAX_NAME]
    if name not in EVENT_ALLOWLIST:
        return None

    raw_props = event.get("props")
    props: Dict[str, Any] = {}
    if isinstance(raw_props, dict):
        for key, value in list(raw_props.items())[:_MAX_PROPS]:
            expected = PROP_SCHEMA.get(key)
            if expected is None:
                continue
            cleaned = _clean_value(value)
            if cleaned is None:
                continue
            if expected is int and not isinstance(cleaned, int):
                continue
            props[key] = cleaned

    ts = event.get("ts")
    if not isinstance(ts, (int, float)) or isinstance(ts, bool):
        ts = None

    return {"name": name, "props": props, "ts": ts}


def record_events(
    events: Iterable[Any],
    session_id: Optional[str] = None,
    *,
    now: Optional[datetime] = None,
) -> Dict[str, int]:
    """Append sanitised events to today's local file. Returns accepted/rejected.

    Never raises: analytics must not be able to break a request, so any I/O
    failure is logged and reported as zero accepted.
    """
    accepted = 0
    rejected = 0
    clean: List[Dict[str, Any]] = []

    safe_session = session_id if (session_id and is_valid_session_id(session_id)) else None

    for event in list(events)[:_MAX_EVENTS_PER_BATCH]:
        sanitized = sanitize_event(event)
        if sanitized is None:
            rejected += 1
            continue
        if safe_session:
            sanitized["session"] = safe_session
        sanitized["at"] = (now or datetime.now(timezone.utc)).isoformat()
        clean.append(sanitized)
        accepted += 1

    if not clean:
        return {"accepted": 0, "rejected": rejected}

    try:
        os.makedirs(ANALYTICS_DIR, exist_ok=True)
        with open(_daily_path(_today(now)), "a", encoding="utf-8") as handle:
            for row in clean:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:  # noqa: BLE001 - never fail the caller over analytics
        logger.warning("[analytics] could not write events: %s", exc)
        return {"accepted": 0, "rejected": rejected + accepted}

    return {"accepted": accepted, "rejected": rejected}


def _read_day(day: str) -> List[Dict[str, Any]]:
    path = _daily_path(day)
    rows: List[Dict[str, Any]] = []
    if not os.path.exists(path):
        return rows
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get("name") in EVENT_ALLOWLIST:
                    rows.append(row)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[analytics] could not read %s: %s", day, exc)
    return rows


def summarize(days: int = 7, *, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Deterministic funnel + counts over the last ``days`` days.

    Counts are pure arithmetic over the local files, so the same data always
    produces the same summary — no sampling, no approximation.
    """
    days = max(1, min(int(days or 7), RETENTION_DAYS))
    current = now or datetime.now(timezone.utc)

    by_name: Dict[str, int] = {}
    sessions: set = set()
    total = 0

    for offset in range(days):
        day = _today(current - timedelta(days=offset))
        for row in _read_day(day):
            name = row.get("name", "")
            by_name[name] = by_name.get(name, 0) + 1
            total += 1
            session = row.get("session")
            if isinstance(session, str) and session:
                sessions.add(session)

    funnel = []
    first_count = by_name.get(FUNNEL_STEPS[0], 0) if FUNNEL_STEPS else 0
    for step in FUNNEL_STEPS:
        count = by_name.get(step, 0)
        rate = round(count / first_count, 3) if first_count else 0.0
        funnel.append({"step": step, "count": count, "rate": rate})

    return {
        "days": days,
        "generated_at": current.isoformat(),
        "total_events": total,
        "unique_sessions": len(sessions),
        "by_name": dict(sorted(by_name.items())),
        "funnel": funnel,
    }


def cleanup_analytics(*, now: Optional[datetime] = None) -> int:
    """Delete daily files older than ``RETENTION_DAYS``. Returns files removed."""
    current = now or datetime.now(timezone.utc)
    cutoff = (current - timedelta(days=RETENTION_DAYS)).date()
    removed = 0
    if not os.path.isdir(ANALYTICS_DIR):
        return 0
    for filename in os.listdir(ANALYTICS_DIR):
        if not filename.endswith(".jsonl"):
            continue
        stem = filename[: -len(".jsonl")]
        try:
            day = datetime.strptime(stem, "%Y-%m-%d").date()
        except ValueError:
            continue
        if day < cutoff:
            try:
                os.remove(os.path.join(ANALYTICS_DIR, filename))
                removed += 1
            except OSError:
                continue
    return removed
