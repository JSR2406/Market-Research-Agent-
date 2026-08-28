import os
import json
import logging
import time
from pathlib import Path

logger = logging.getLogger(__name__)
SESSIONS_DIR = Path(os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions"))

def _init_dir():
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

def save_session(session_id: str, topic: str, state: dict):
    _init_dir()
    file_path = SESSIONS_DIR / f"{session_id}.json"
    data = {
        "session_id": session_id,
        "topic": topic,
        "state": state,
        "updated_at": time.time()
    }
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save session {session_id}: {e}")

def load_last_session(session_id: str):
    file_path = SESSIONS_DIR / f"{session_id}.json"
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {e}")
    return None

def build_resume_context(prior_data: dict) -> str:
    topic = prior_data.get("topic", "")
    state = prior_data.get("state", {})
    final_report = state.get("final_report", "")
    
    business_summary = ""
    try:
        if final_report:
            clean_json = final_report.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean_json)
            business_summary = parsed.get("business_summary", "")
    except Exception:
        business_summary = final_report[:200]
        
    return f"Previous business context: {topic}. Summary: {business_summary}"

def delete_session(session_id: str):
    file_path = SESSIONS_DIR / f"{session_id}.json"
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

def cleanup_old_sessions() -> int:
    """Delete sessions older than 7 days"""
    _init_dir()
    deleted = 0
    now = time.time()
    try:
        for f in SESSIONS_DIR.glob("*.json"):
            if f.is_file():
                mtime = f.stat().st_mtime
                if now - mtime > 7 * 24 * 60 * 60:
                    f.unlink()
                    deleted += 1
    except Exception:
        pass
    return deleted
