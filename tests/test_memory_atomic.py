from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import tempfile
import threading
import time
import uuid
from collections import defaultdict
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

_FILE_LOCKS: Dict[str, threading.Lock] = {}
_FILE_LOCK_GUARD = threading.Lock()


def _file_lock(key: str) -> threading.Lock:
    with _FILE_LOCK_GUARD:
        lock = _FILE_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _FILE_LOCKS[key] = lock
        return lock


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON atomically to avoid truncated files during concurrent updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


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
    with _file_lock(f"{subdir}:{id}"):
        _atomic_write(p, data)


def _delete(subdir: Path, id: str) -> None:
    p = _path(subdir, id)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass
