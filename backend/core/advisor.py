"""
backend/core/advisor.py — advisor workspace repository + authentication.

JSON-backed (no Prisma/Postgres — matches the rest of the backend). Every
advisor-owned entity lives as a file under ``backend/sessions/advisor/``:

    advisors/{id}.json      the advisor (email, password hash, plan, locale…)
    sessions/{id}.json      a signed session (hashed token + expiry)
    clients/{id}.json       one business profile owned by an advisor
    notes/{id}.json         one free-text advisor note on a client
    snapshots/{id}.json     one stored eligibility run for a client
    reports/{id}.json       one generated combined / single-client report

The repository is the **only** place that touches these files, and every
method takes ``advisor_id`` and injects it into the query. Cross-advisor
leakage is therefore impossible by construction: there is no code path that
reads or writes another advisor's records.

Auth is email + password. Passwords are hashed with PBKDF2-HMAC-SHA256
(stdlib, no new dependency). A session is a random bearer token, hashed and
stored with an expiry; the plain token is returned to the caller, which sends
it as an ``Authorization: Bearer <token>`` header. A bearer header works
cross-origin (the app is deployed frontend-on-Vercel / backend-on-Render),
unlike an httpOnly cookie, and is just as easy to rotate or revoke.

The isolation rule — every query is scoped by advisorId — is the security
foundation of WS-11 and is unit-tested in tests/test_advisor_repo.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SESSIONS_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions"))  # backend/sessions/
ADVISOR_DIR = SESSIONS_DIR / "advisor"

# --- entity subdirectories ---------------------------------------------------
_ADVISORS = ADVISOR_DIR / "advisors"
_SESSIONS = ADVISOR_DIR / "sessions"
_CLIENTS = ADVISOR_DIR / "clients"
_NOTES = ADVISOR_DIR / "notes"
_SNAPSHOTS = ADVISOR_DIR / "snapshots"
_REPORTS = ADVISOR_DIR / "reports"

# A session lives 7 days.
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60

ENGINE_VERSION = "elig-1.0.0"

MAX_BATCH = 200  # cap for the bulk eligibility endpoint

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _is_valid_id(value: str) -> bool:
    return isinstance(value, str) and bool(_ID_RE.match(value))


def _init_dirs() -> None:
    for d in (_ADVISORS, _SESSIONS, _CLIENTS, _NOTES, _SNAPSHOTS, _REPORTS):
        d.mkdir(parents=True, exist_ok=True)


def _path(subdir: Path, id: str) -> Path:
    return subdir / f"{id}.json"


def _read(subdir: Path, id: str) -> Optional[Dict[str, Any]]:
    p = _path(subdir, id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:  # corrupt file → treat as missing, never crash
        logger.warning("[advisor] corrupt file %s: %s", p, exc)
        return None


def _write(subdir: Path, id: str, data: Dict[str, Any]) -> None:
    _init_dirs()
    p = _path(subdir, id)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _delete(subdir: Path, id: str) -> None:
    p = _path(subdir, id)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def _list(subdir: Path) -> List[Dict[str, Any]]:
    _init_dirs()
    out: List[Dict[str, Any]] = []
    for p in sorted(subdir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                out.append(data)
        except Exception:
            continue
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Password hashing (stdlib only — PBKDF2-HMAC-SHA256)
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000)
    return f"{salt}$${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, dk = stored.split("$$", 1)
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), 100_000
        )
        return secrets.compare_digest(check.hex(), dk)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Advisors
# ─────────────────────────────────────────────────────────────────────────────

def _advisor_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Linear scan — advisor counts are tiny (one advisor, a firm at most)."""
    want = (email or "").strip().lower()
    if not want:
        return None
    for data in _list(_ADVISORS):
        if (data.get("email") or "").strip().lower() == want:
            return data
    return None


def create_advisor(
    *,
    email: str,
    password: str,
    name: str = "",
    org_name: Optional[str] = None,
    phone: Optional[str] = None,
    locale: str = "en",
    plan: str = "free",
) -> Optional[Dict[str, Any]]:
    """Create an advisor. Returns None when the email is already taken."""
    _init_dirs()
    if _advisor_by_email(email):
        return None
    advisor_id = str(uuid.uuid4())
    now = time.time()
    advisor: Dict[str, Any] = {
        "id": advisor_id,
        "email": email.strip().lower(),
        "name": name.strip(),
        "org_name": (org_name or "").strip(),
        "phone": (phone or "").strip(),
        "locale": locale if locale in ("en", "hi") else "en",
        "plan": plan,
        "password_hash": hash_password(password),
        "created_at": now,
        "updated_at": now,
    }
    _write(_ADVISORS, advisor_id, advisor)
    return advisor


def authenticate_advisor(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify credentials; return the advisor (without its password hash) or None."""
    advisor = _advisor_by_email(email)
    if not advisor:
        return None
    if not verify_password(password, advisor.get("password_hash", "")):
        return None
    safe = dict(advisor)
    safe.pop("password_hash", None)
    return safe


def get_advisor(advisor_id: str) -> Optional[Dict[str, Any]]:
    if not _is_valid_id(advisor_id):
        return None
    data = _read(_ADVISORS, advisor_id)
    if not data:
        return None
    safe = dict(data)
    safe.pop("password_hash", None)
    return safe


def update_advisor(
    advisor_id: str, *, name: Optional[str] = None, org_name: Optional[str] = None,
    phone: Optional[str] = None, locale: Optional[str] = None, plan: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    advisor = get_advisor(advisor_id)
    if not advisor:
        return None
    if name is not None:
        advisor["name"] = name.strip()
    if org_name is not None:
        advisor["org_name"] = org_name.strip()
    if phone is not None:
        advisor["phone"] = phone.strip()
    if locale is not None:
        advisor["locale"] = locale if locale in ("en", "hi") else advisor.get("locale", "en")
    if plan is not None:
        advisor["plan"] = plan
    advisor["updated_at"] = time.time()
    # restore the hash so the file stays complete
    full = _read(_ADVISORS, advisor_id) or {}
    advisor["password_hash"] = full.get("password_hash", "")
    _write(_ADVISORS, advisor_id, advisor)
    advisor.pop("password_hash", None)
    return advisor


def change_password(advisor_id: str, current_password: str, new_password: str) -> bool:
    advisor = _read(_ADVISORS, advisor_id)
    if not advisor or not verify_password(current_password, advisor.get("password_hash", "")):
        return False
    advisor["password_hash"] = hash_password(new_password)
    advisor["updated_at"] = time.time()
    _write(_ADVISORS, advisor_id, advisor)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Sessions (bearer tokens)
# ─────────────────────────────────────────────────────────────────────────────

def create_session(advisor_id: str) -> Optional[str]:
    """Issue a bearer token for an advisor. Returns the plain token (once)."""
    if not get_advisor(advisor_id):
        return None
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.time()
    session: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "advisor_id": advisor_id,
        "token_hash": token_hash,
        "expires_at": now + SESSION_TTL_SECONDS,
        "created_at": now,
    }
    _write(_SESSIONS, session["id"], session)
    return token


def get_session(token: str) -> Optional[Dict[str, Any]]:
    """Validate a bearer token; return the advisor (safe) or None."""
    for data in _list(_SESSIONS):
        if data.get("token_hash") == hashlib.sha256(token.encode("utf-8")).hexdigest():
            if data.get("expires_at", 0) < time.time():
                _delete(_SESSIONS, data["id"])
                return None
            advisor = get_advisor(data.get("advisor_id", ""))
            return advisor
    return None


def delete_session(token: str) -> None:
    for data in _list(_SESSIONS):
        if data.get("token_hash") == hashlib.sha256(token.encode("utf-8")).hexdigest():
            _delete(_SESSIONS, data["id"])
            return


# ─────────────────────────────────────────────────────────────────────────────
# Clients — every method is scoped by advisor_id (isolation key)
# ─────────────────────────────────────────────────────────────────────────────

def create_client(
    advisor_id: str, *, label: str, profile: Dict[str, Any],
    sector: Optional[str] = None, state: Optional[str] = None, stage: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    if not get_advisor(advisor_id):
        return None
    client_id = str(uuid.uuid4())
    now = time.time()
    client: Dict[str, Any] = {
        "id": client_id,
        "advisor_id": advisor_id,
        "label": label.strip(),
        "profile": profile if isinstance(profile, dict) else {},
        "sector": (sector or "").strip() or None,
        "state": (state or "").strip() or None,
        "stage": (stage or "").strip() or None,
        "readiness": None,
        "created_at": now,
        "updated_at": now,
    }
    _write(_CLIENTS, client_id, client)
    return client


def list_clients(advisor_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for c in _list(_CLIENTS):
        if c.get("advisor_id") != advisor_id:
            continue
        safe = {k: c.get(k) for k in (
            "id", "label", "profile", "sector", "state", "stage",
            "readiness", "created_at", "updated_at",
        )}
        out.append(safe)
    out.sort(key=lambda c: c.get("updated_at") or 0, reverse=True)
    return out


def get_client(advisor_id: str, client_id: str) -> Optional[Dict[str, Any]]:
    if not _is_valid_id(client_id):
        return None
    c = _read(_CLIENTS, client_id)
    if not c or c.get("advisor_id") != advisor_id:
        return None
    return c


def update_client(
    advisor_id: str, client_id: str, *, label: Optional[str] = None,
    profile: Optional[Dict[str, Any]] = None, sector: Optional[str] = None,
    state: Optional[str] = None, stage: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    c = get_client(advisor_id, client_id)
    if not c:
        return None
    if label is not None:
        c["label"] = label.strip()
    if profile is not None:
        c["profile"] = profile
    if sector is not None:
        c["sector"] = sector.strip() or None
    if state is not None:
        c["state"] = state.strip() or None
    if stage is not None:
        c["stage"] = stage.strip() or None
    c["updated_at"] = time.time()
    _write(_CLIENTS, client_id, c)
    return c


def delete_client(advisor_id: str, client_id: str) -> bool:
    c = get_client(advisor_id, client_id)
    if not c:
        return False
    _delete(_CLIENTS, client_id)
    # Cascade: notes, snapshots, reports referencing this client are removed
    # by the caller in a transaction-like manner (see delete_client_cascade).
    return True


def delete_client_cascade(advisor_id: str, client_id: str) -> bool:
    """Delete a client and everything that references it (notes, snapshots)."""
    if not delete_client(advisor_id, client_id):
        return False
    for n in _list(_NOTES):
        if n.get("client_id") == client_id and n.get("advisor_id") == advisor_id:
            _delete(_NOTES, n["id"])
    for s in _list(_SNAPSHOTS):
        if s.get("client_id") == client_id and s.get("advisor_id") == advisor_id:
            _delete(_SNAPSHOTS, s["id"])
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────────────────

def add_note(
    advisor_id: str, client_id: str, body: str,
) -> Optional[Dict[str, Any]]:
    if not get_client(advisor_id, client_id):
        return None
    note_id = str(uuid.uuid4())
    now = time.time()
    note: Dict[str, Any] = {
        "id": note_id,
        "advisor_id": advisor_id,
        "client_id": client_id,
        "body": body.strip(),
        "created_at": now,
    }
    _write(_NOTES, note_id, note)
    return note


def list_notes(advisor_id: str, client_id: str) -> List[Dict[str, Any]]:
    if not get_client(advisor_id, client_id):
        return []
    out: List[Dict[str, Any]] = []
    for n in _list(_NOTES):
        if n.get("advisor_id") != advisor_id or n.get("client_id") != client_id:
            continue
        out.append({k: n.get(k) for k in ("id", "body", "created_at")})
    out.sort(key=lambda n: n.get("created_at") or 0, reverse=True)
    return out


def delete_note(advisor_id: str, note_id: str) -> bool:
    if not _is_valid_id(note_id):
        return False
    n = _read(_NOTES, note_id)
    if not n or n.get("advisor_id") != advisor_id:
        return False
    _delete(_NOTES, note_id)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility snapshots
# ─────────────────────────────────────────────────────────────────────────────

def save_snapshot(
    advisor_id: str, client_id: str, engine_version: str, results: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    if not get_client(advisor_id, client_id):
        return None
    snapshot_id = str(uuid.uuid4())
    now = time.time()
    snapshot: Dict[str, Any] = {
        "id": snapshot_id,
        "advisor_id": advisor_id,
        "client_id": client_id,
        "engine_version": engine_version,
        "results": results,
        "run_at": now,
    }
    _write(_SNAPSHOTS, snapshot_id, snapshot)
    # Refresh the client's cached readiness from this run.
    _refresh_readiness(advisor_id, client_id, results)
    return snapshot


def _refresh_readiness(advisor_id: str, client_id: str, results: Dict[str, Any]) -> None:
    c = _read(_CLIENTS, client_id)
    if not c or c.get("advisor_id") != advisor_id:
        return
    ranked = results.get("ranked") or []
    best = max((r.get("score") or 0 for r in ranked), default=0)
    c["readiness"] = int(max(0, min(100, best)))
    c["updated_at"] = time.time()
    _write(_CLIENTS, client_id, c)


def get_latest_snapshot(advisor_id: str, client_id: str) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    for s in _list(_SNAPSHOTS):
        if s.get("advisor_id") != advisor_id or s.get("client_id") != client_id:
            continue
        if best is None or s.get("run_at", 0) > best.get("run_at", 0):
            best = s
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────

def create_report(
    advisor_id: str, *, kind: str, client_ids: List[str], locale: str, file_path: str,
) -> Optional[Dict[str, Any]]:
    if not get_advisor(advisor_id):
        return None
    report_id = str(uuid.uuid4())
    now = time.time()
    report: Dict[str, Any] = {
        "id": report_id,
        "advisor_id": advisor_id,
        "kind": kind,
        "client_ids": client_ids,
        "locale": locale,
        "file_path": file_path,
        "created_at": now,
    }
    _write(_REPORTS, report_id, report)
    return report


def list_reports(advisor_id: str) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for r in _list(_REPORTS):
        if r.get("advisor_id") != advisor_id:
            continue
        out.append({k: r.get(k) for k in ("id", "kind", "client_ids", "locale",
                                          "file_path", "created_at")})
    out.sort(key=lambda r: r.get("created_at") or 0, reverse=True)
    return out


def get_report(advisor_id: str, report_id: str) -> Optional[Dict[str, Any]]:
    if not _is_valid_id(report_id):
        return None
    r = _read(_REPORTS, report_id)
    if not r or r.get("advisor_id") != advisor_id:
        return None
    return r


def delete_report(advisor_id: str, report_id: str) -> bool:
    r = get_report(advisor_id, report_id)
    if not r:
        return False
    _delete(_REPORTS, report_id)
    return True


def hard_delete_advisor(advisor_id: str) -> None:
    """GDPR-style hard delete: advisor, sessions, clients, notes, snapshots, reports."""
    _delete(_ADVISORS, advisor_id)
    for s in _list(_SESSIONS):
        if s.get("advisor_id") == advisor_id:
            _delete(_SESSIONS, s["id"])
    for c in _list(_CLIENTS):
        if c.get("advisor_id") == advisor_id:
            delete_client_cascade(advisor_id, c["id"])
    for n in _list(_NOTES):
        if n.get("advisor_id") == advisor_id:
            _delete(_NOTES, n["id"])
    for s in _list(_SNAPSHOTS):
        if s.get("advisor_id") == advisor_id:
            _delete(_SNAPSHOTS, s["id"])
    for r in _list(_REPORTS):
        if r.get("advisor_id") == advisor_id:
            _delete(_REPORTS, r["id"])
