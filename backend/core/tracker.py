"""
tracker.py — applications, deadlines and alerts (WS-6).

The advisory flow answers "which schemes fit you"; this module answers the next
question, "did you actually apply". Two rules from the project's data principles
shape it:

* **Deadlines are curated, never invented.** `backend/data/deadlines.json` holds
  only windows we can point at a URL for, each with ``last_verified_at``. Every
  other scheme is reported as **rolling** ("no closing date published") rather
  than given a plausible-looking date, and the user can put their *own* target
  date on an application.
* **The "closing soon" flag is arithmetic**, not a model judgement:
  ``deadline_state()`` compares a date to today and flags anything inside a
  14-day window. It is pure and offline, so it works with every provider down.

Applications are stored per session id in ``backend/sessions/{id}_tracker.json``,
the same shape and the same allowlist guard as the chat history. Nothing is
written without a valid session id.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.core.heuristics import load_schemes
from backend.core.memory import SESSIONS_DIR, is_valid_session_id

logger = logging.getLogger(__name__)

DATA_PATH = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "deadlines.json"))

# ── application statuses ──────────────────────────────────────────────────────
STATUSES = ["planning", "docs_ready", "submitted", "approved", "rejected"]
STATUS_LABELS: Dict[str, Dict[str, str]] = {
    "planning": {"en": "Planning", "hi": "सोच रहे हैं"},
    "docs_ready": {"en": "Documents ready", "hi": "कागज़ तैयार"},
    "submitted": {"en": "Submitted", "hi": "जमा किया"},
    "approved": {"en": "Approved", "hi": "मंज़ूर"},
    "rejected": {"en": "Not approved", "hi": "नामंज़ूर"},
}
TERMINAL_STATUSES = {"approved", "rejected"}

# ── deadline states ───────────────────────────────────────────────────────────
STATE_OPEN = "open"
STATE_SOON = "closing_soon"
STATE_LAPSED = "lapsed"
STATE_LAPSED_PENDING = "lapsed_pending"
STATE_ROLLING = "rolling"

STATE_LABELS: Dict[str, Dict[str, str]] = {
    STATE_OPEN: {"en": "Open", "hi": "खुला"},
    STATE_SOON: {"en": "Closing soon", "hi": "जल्द बंद हो रहा है"},
    STATE_LAPSED: {"en": "Window over", "hi": "अवधि ख़त्म"},
    STATE_LAPSED_PENDING: {"en": "Awaiting confirmation", "hi": "पुष्टि बाक़ी"},
    STATE_ROLLING: {"en": "Rolling — no closing date", "hi": "लगातार — कोई अंतिम तिथि नहीं"},
}

CLOSING_SOON_DAYS = 14
MAX_NOTE_CHARS = 500
MAX_APPLICATIONS = 50
# Nudges about newly matched schemes stop at this many: an alert that lists
# twenty schemes is a catalogue, and gets ignored.
MAX_NEW_MATCHES = 5

DISCLAIMER = {
    "en": (
        "Dates come from the scheme's own documents and are re-checked by hand. "
        "Always confirm the window with the bank or nodal agency before you travel."
    ),
    "hi": (
        "तारीख़ें स्कीम के अपने दस्तावेज़ों से हैं और हाथ से दोबारा जाँची जाती हैं। "
        "दफ़्तर जाने से पहले बैंक या नोडल एजेंसी से अवधि ज़रूर पक्की करें।"
    ),
}

ALERT_EVENTS = ["deadline_soon", "new_match", "reverified"]
ALERT_CHANNELS = ["whatsapp", "email"]


def _t(lang: str, en: str, hi: str) -> str:
    return hi if lang == "hi" else en


# ── curated deadlines ─────────────────────────────────────────────────────────

def parse_date(value: Any) -> Optional[date]:
    """ISO ``YYYY-MM-DD`` → date, anything else → None (never raises)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.strptime(str(value or "").strip(), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def load_deadlines(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """
    Read the curated deadline rows; a malformed row is dropped, not guessed at.

    A row without a parseable date would silently become "rolling", which is the
    one thing it must never do, so it is skipped and logged instead.
    """
    source = path or DATA_PATH
    try:
        with open(source, encoding="utf-8") as handle:
            rows = json.load(handle)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError):
        logger.warning("[tracker] deadlines.json could not be read", exc_info=True)
        return []
    if not isinstance(rows, list):
        return []

    cleaned: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        when = parse_date(row.get("date"))
        if when is None:
            logger.warning("[tracker] dropping deadline without a valid date: %r", row.get("scheme_id"))
            continue
        cleaned.append(
            {
                "scheme_id": str(row.get("scheme_id") or ""),
                "kind": str(row.get("kind") or "window"),
                "date": when.isoformat(),
                "title": row.get("title") if isinstance(row.get("title"), dict) else {},
                "note": row.get("note") if isinstance(row.get("note"), dict) else {},
                "source_url": str(row.get("source_url") or ""),
                "last_verified_at": str(row.get("last_verified_at") or ""),
            }
        )
    return cleaned


def deadline_state(
    when: Any,
    today: Optional[date] = None,
    kind: str = "window",
    window_days: int = CLOSING_SOON_DAYS,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Classify one date. ``window_days`` is inclusive of today.

    A ``window_pending`` row whose date has passed is *not* called closed: the
    window lapsed but a renewal is on the table, and telling a user "closed"
    when the ministry has proposed an extension would send them away for good.
    """
    today = today or date.today()
    parsed = parse_date(when)
    if parsed is None:
        return {
            "state": STATE_ROLLING,
            "days_left": None,
            "state_label": STATE_LABELS[STATE_ROLLING][lang if lang == "hi" else "en"],
        }
    days_left = (parsed - today).days
    label = STATE_LABELS
    if days_left < 0:
        state = STATE_LAPSED_PENDING if kind in ("window_pending", "pending") else STATE_LAPSED
    elif days_left <= window_days:
        state = STATE_SOON
    else:
        state = STATE_OPEN
    return {
        "state": state,
        "days_left": days_left,
        "state_label": label[state]["hi" if lang == "hi" else "en"],
    }


# ── applications ──────────────────────────────────────────────────────────────

def _scheme_index() -> Dict[str, Dict[str, Any]]:
    return {str(record.get("id")): record for record in load_schemes()}


def validate_application(payload: Any) -> Dict[str, Any]:
    """
    Normalise one application row or raise ``ValueError``.

    The scheme id must exist in the curated dataset — an id we cannot look up
    would put a card on the board with no source behind it.
    """
    if not isinstance(payload, dict):
        raise ValueError("Each application must be an object.")
    scheme_id = str(payload.get("scheme_id") or "").strip()
    scheme = _scheme_index().get(scheme_id)
    if not scheme:
        raise ValueError("Unknown scheme.")
    status = str(payload.get("status") or "planning").strip()
    if status not in STATUSES:
        raise ValueError("Unknown status.")
    target = str(payload.get("target_date") or "").strip()
    if target and parse_date(target) is None:
        raise ValueError("Target date must look like YYYY-MM-DD.")
    family = str(scheme.get("tier_group") or scheme_id)
    return {
        "scheme_id": scheme_id,
        "scheme_name": str(scheme.get("scheme_name") or scheme_id),
        "tier_group": family,
        "status": status,
        "status_label": STATUS_LABELS[status]["en"],
        "target_date": target,
        "notes": str(payload.get("notes") or "")[:MAX_NOTE_CHARS],
        "source_url": str(scheme.get("source_url") or ""),
        "last_verified_at": str(scheme.get("last_verified_at") or ""),
    }


def validate_applications(payload: Any) -> List[Dict[str, Any]]:
    if payload is None:
        return []
    if not isinstance(payload, list):
        raise ValueError("Applications must be a list.")
    if len(payload) > MAX_APPLICATIONS:
        raise ValueError("Too many applications.")
    rows: List[Dict[str, Any]] = []
    seen: set = set()
    for item in payload:
        row = validate_application(item)
        # One card per programme: tracking two MUDRA tiers is the same effort.
        if row["tier_group"] in seen:
            continue
        seen.add(row["tier_group"])
        rows.append(row)
    return rows


def _tracker_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}_tracker.json"


def load_tracker(session_id: str) -> Dict[str, Any]:
    """Read a session's tracker; an unusable id or file yields an empty board."""
    if not is_valid_session_id(session_id):
        return {"applications": [], "alert": {}}
    try:
        with open(_tracker_path(session_id), encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"applications": [], "alert": {}}
    applications = data.get("applications") if isinstance(data, dict) else None
    alert = data.get("alert") if isinstance(data, dict) else None
    return {
        "applications": applications if isinstance(applications, list) else [],
        "alert": alert if isinstance(alert, dict) else {},
    }


def save_tracker(session_id: str, applications: List[Dict[str, Any]], alert: Optional[Dict[str, Any]] = None) -> None:
    """Persist the tracker. An invalid session id raises — no silent no-op."""
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid session id.")
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "applications": applications,
        "alert": alert or {},
        "updated_at": time.time(),
    }
    with open(_tracker_path(session_id), "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def delete_tracker(session_id: str) -> None:
    """Remove the tracker file (used when a session is deleted)."""
    if not is_valid_session_id(session_id):
        return
    try:
        _tracker_path(session_id).unlink(missing_ok=True)
    except OSError:
        logger.debug("[tracker] could not remove tracker for %s", session_id, exc_info=True)


# ── the board ─────────────────────────────────────────────────────────────────

def build_board(
    applications: Optional[List[Dict[str, Any]]] = None,
    today: Optional[date] = None,
    lang: str = "en",
    window_days: int = CLOSING_SOON_DAYS,
    deadlines: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Merge curated deadlines, rolling programmes and the user's own targets into
    one calendar, sorted by urgency.
    """
    lang = "hi" if lang == "hi" else "en"
    today = today or date.today()
    applications = applications or []
    curated = deadlines if deadlines is not None else load_deadlines()
    schemes = _scheme_index()
    tracked_families = {row.get("tier_group") for row in applications if row.get("tier_group")}

    rows: List[Dict[str, Any]] = []

    for deadline in curated:
        scheme = schemes.get(deadline["scheme_id"]) or {}
        family = str(scheme.get("tier_group") or deadline["scheme_id"])
        state = deadline_state(deadline["date"], today, deadline["kind"], window_days, lang)
        # With a tracker, show deadlines for the schemes being tracked plus
        # anything about to close (a window the user never added still matters).
        if tracked_families and family not in tracked_families and state["state"] != STATE_SOON:
            continue
        rows.append(
            {
                "source": "scheme",
                "scheme_id": deadline["scheme_id"],
                "scheme_name": str(scheme.get("scheme_name") or deadline["scheme_id"]),
                "tier_group": family,
                "kind": deadline["kind"],
                "date": deadline["date"],
                "title": deadline["title"].get(lang) or deadline["title"].get("en") or "",
                "note": deadline["note"].get(lang) or deadline["note"].get("en") or "",
                "source_url": deadline["source_url"],
                "last_verified_at": deadline["last_verified_at"],
                **state,
            }
        )

    # User targets — their own dates, flagged the same way.
    for application in applications:
        target = application.get("target_date")
        if not target:
            continue
        state = deadline_state(target, today, "target", window_days, lang)
        rows.append(
            {
                "source": "yours",
                "scheme_id": application.get("scheme_id", ""),
                "scheme_name": application.get("scheme_name", ""),
                "tier_group": application.get("tier_group", ""),
                "kind": "target",
                "date": str(target),
                "title": _t(lang, "Your target date", "आपकी तय तारीख़"),
                "note": "",
                "source_url": application.get("source_url", ""),
                "last_verified_at": "",
                **state,
            }
        )

    # Programmes with no published window at all — say so instead of staying quiet.
    curated_families = {row["tier_group"] for row in rows if row["source"] == "scheme"}
    for application in applications:
        family = str(application.get("tier_group") or application.get("scheme_id") or "")
        if not family or family in curated_families:
            continue
        curated_families.add(family)
        rows.append(
            {
                "source": "scheme",
                "scheme_id": application.get("scheme_id", ""),
                "scheme_name": application.get("scheme_name", ""),
                "tier_group": family,
                "kind": "rolling",
                "date": "",
                "title": _t(lang, "No closing date published", "कोई अंतिम तिथि प्रकाशित नहीं"),
                "note": _t(
                    lang,
                    "This scheme accepts applications continuously. Set your own target date to keep it moving.",
                    "यह स्कीम लगातार आवेदन लेती है। काम आगे बढ़ाने के लिए अपनी तारीख़ तय करें।",
                ),
                "source_url": application.get("source_url", ""),
                "last_verified_at": application.get("last_verified_at", ""),
                **deadline_state(None, today, "rolling", window_days, lang),
            }
        )

    def sort_key(row: Dict[str, Any]):
        rolling = 1 if row["state"] == STATE_ROLLING else 0
        when = parse_date(row["date"]) or date.max
        return (rolling, when, row["scheme_name"])

    rows.sort(key=sort_key)

    counts = {state: 0 for state in STATE_LABELS}
    for row in rows:
        counts[row["state"]] = counts.get(row["state"], 0) + 1

    return {
        "rows": rows,
        "closing_soon": [row for row in rows if row["state"] == STATE_SOON],
        "rolling": [row for row in rows if row["state"] == STATE_ROLLING],
        "counts": counts,
        "today": today.isoformat(),
        "window_days": window_days,
        "disclaimer": DISCLAIMER[lang],
    }


# ── alerts ────────────────────────────────────────────────────────────────────

def validate_alert(payload: Any, lang: str = "en") -> Dict[str, Any]:
    """
    Normalise an alert subscription. Consent is mandatory and explicit: this
    touches a phone number, and an implicit opt-in is not an opt-in.
    """
    if payload in (None, {}):
        return {}
    if not isinstance(payload, dict):
        raise ValueError("Alert settings must be an object.")
    channel = str(payload.get("channel") or "").strip()
    if channel not in ALERT_CHANNELS:
        raise ValueError("Alert channel must be whatsapp or email.")
    value = str(payload.get("value") or "").strip()
    if channel == "whatsapp" and (not value.isdigit() or not 10 <= len(value) <= 15):
        raise ValueError("Enter a phone number with country code, digits only.")
    if channel == "email" and ("@" not in value or len(value) > 200 or " " in value):
        raise ValueError("Enter a valid email address.")
    events = [e for e in (payload.get("events") or []) if e in ALERT_EVENTS]
    if not events:
        events = list(ALERT_EVENTS)
    if not payload.get("consent"):
        raise ValueError("Consent is required to send alerts.")
    return {"channel": channel, "value": value, "events": events, "consent": True}


def build_alerts(
    applications: Optional[List[Dict[str, Any]]] = None,
    board: Optional[Dict[str, Any]] = None,
    previous_verified: Optional[Dict[str, str]] = None,
    intake: Optional[Dict[str, str]] = None,
    topic: str = "",
    today: Optional[date] = None,
    lang: str = "en",
) -> Dict[str, Any]:
    """
    The messages that would be sent, built deterministically.

    Three events: a deadline inside the window, a scheme whose curated record was
    re-verified since the user last looked, and a newly matched scheme they are
    not tracking yet. No message is written unless its trigger actually holds.
    """
    lang = "hi" if lang == "hi" else "en"
    applications = applications or []
    board = board or build_board(applications, today, lang)
    previous_verified = previous_verified or {}
    schemes = _scheme_index()

    messages: List[Dict[str, str]] = []

    for row in board.get("closing_soon") or []:
        days = row.get("days_left")
        if row.get("kind") == "target":
            message = _t(
                lang,
                f"Your target date for {row.get('scheme_name')} is in {days} day(s) ({row.get('date')}).",
                f"{row.get('scheme_name')} के लिए आपकी तारीख़ {days} दिन में है ({row.get('date')})।",
            )
        else:
            message = _t(
                lang,
                f"{row.get('scheme_name')}: the application window closes in {days} day(s) on {row.get('date')}.",
                f"{row.get('scheme_name')}: आवेदन की अवधि {days} दिन में {row.get('date')} को बंद हो रही है।",
            )
        messages.append(
            {
                "event": "deadline_soon",
                "scheme_id": row.get("scheme_id", ""),
                "message": message,
            }
        )

    if intake:
        from backend.core.eligibility import evaluate_schemes

        result = evaluate_schemes(intake, topic, None, lang)
        tracked_families = {
            str(a.get("tier_group") or a.get("scheme_id")) for a in applications if a.get("scheme_id")
        }
        seen_families = set(tracked_families)
        extra = 0
        # `ranked` is the engine's scored, best-first list of open schemes, so
        # the nudges lead with the strongest match and stop there: a 20-line
        # catalogue is not an alert. Tiered programmes collapse to one family
        # (MUDRA is one scheme to the user, not four).
        for verdict in result.get("ranked") or []:
            family = str(verdict.get("tier_group") or verdict.get("scheme_id") or "")
            if not family or family in seen_families:
                continue
            if len(seen_families) - len(tracked_families) >= MAX_NEW_MATCHES:
                extra += 1
                continue
            seen_families.add(family)
            messages.append(
                {
                    "event": "new_match",
                    "scheme_id": str(verdict.get("scheme_id") or ""),
                    "message": _t(
                        lang,
                        f"New match: {verdict.get('name')} — add it to your tracker.",
                        f"नई स्कीम मिली: {verdict.get('name')} — ट्रैकर में जोड़ें।",
                    ),
                }
            )
        if extra:
            messages.append(
                {
                    "event": "new_match",
                    "scheme_id": "",
                    "message": _t(
                        lang,
                        f"{extra} more schemes also match your business — see the Schemes page.",
                        f"{extra} और स्कीमें भी आपके बिज़नेस से मिलती हैं — Schemes पेज देखें।",
                    ),
                }
            )

    for application in applications:
        scheme_id = str(application.get("scheme_id") or "")
        record = schemes.get(scheme_id) or {}
        current = str(record.get("last_verified_at") or "")
        seen = str(previous_verified.get(scheme_id) or "")
        if current and seen and current > seen:
            messages.append(
                {
                    "event": "reverified",
                    "scheme_id": scheme_id,
                    "message": _t(
                        lang,
                        f"{record.get('scheme_name') or scheme_id}: our record was re-checked on {current} — re-read the rules.",
                        f"{record.get('scheme_name') or scheme_id}: हमारा रिकॉर्ड {current} को दोबारा जाँचा गया — नियम फिर पढ़ें।",
                    ),
                }
            )

    summary_lines = [_t(lang, "Saathi — your scheme tracker:", "Saathi — आपका स्कीम ट्रैकर:")]
    if messages:
        summary_lines.extend(f"- {m['message']}" for m in messages)
    else:
        summary_lines.append(
            _t(lang, "Nothing needs your attention today.", "आज कुछ ध्यान देने वाला नहीं है।")
        )

    return {
        "messages": messages,
        "summary": "\n".join(summary_lines),
        "checked_on": (today or date.today()).isoformat(),
    }


__all__ = [
    "STATUSES",
    "STATUS_LABELS",
    "STATE_ROLLING",
    "STATE_SOON",
    "CLOSING_SOON_DAYS",
    "DISCLAIMER",
    "ALERT_EVENTS",
    "ALERT_CHANNELS",
    "parse_date",
    "deadline_state",
    "load_deadlines",
    "validate_application",
    "validate_applications",
    "validate_alert",
    "load_tracker",
    "save_tracker",
    "delete_tracker",
    "build_board",
    "build_alerts",
]
