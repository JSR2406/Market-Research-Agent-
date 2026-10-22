import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
SESSIONS_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions"))

# Chat history cap per session (safe window for the LLM context, bounded storage)
MAX_CHAT_MESSAGES = 40

# How many past research runs a session keeps. Enough to compare "before and
# after" without letting a single session grow without bound. The history UI
# reads every one of these (newest first), so this is the size of the stored
# session history.
MAX_RUNS_PER_SESSION = 50

# Session ids are client-controlled and are used to build file paths — they are
# therefore restricted to a strict allowlist (frontend generates `s-<ts>-<rand>`,
# WhatsApp uses `wa-<number>`). Anything else would enable path traversal
# (e.g. `../../data/schemes` resolving outside SESSIONS_DIR).
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_SESSION_LOCKS: Dict[str, threading.Lock] = {}
_SESSION_LOCK_GUARD = threading.Lock()


def _session_lock(session_id: str) -> threading.Lock:
    """Return a process-local lock for a given session id."""
    with _SESSION_LOCK_GUARD:
        key = str(session_id or "")
        lock = _SESSION_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _SESSION_LOCKS[key] = lock
        return lock


def _atomic_write(path: Path, data: Any) -> None:
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


def is_valid_session_id(session_id) -> bool:
    """True when the id is a safe, path-free session identifier."""
    return isinstance(session_id, str) and bool(_SESSION_ID_RE.match(session_id))


def _require_valid_session_id(session_id: str, *, allow_empty: bool = False) -> str:
    if allow_empty and not session_id:
        return session_id
    if not is_valid_session_id(session_id):
        raise ValueError("Invalid session id.")
    return session_id


def _init_dir() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def _session_file(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _chat_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}_chat.json"


# ... existing content continues unchanged below ...
