"""
backend/api/schemas.py — shared pydantic models for the REST surface.

Every router imports its request/response models from here so the OpenAPI
schema, validation caps, and response shapes stay consistent in one place.
Response models are declared on the route (via ``response_model=...``) so
FastAPI validates/serializes what the frontend actually receives.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Strict session-id allowlist (P0 path-traversal guard) — mirrors core.memory.
_SESSION_ID_PATTERN = r"^[A-Za-z0-9_-]{0,64}$"


# ── chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)
    session_id: str = Field("", max_length=64, pattern=_SESSION_ID_PATTERN)
    topic: str = Field("", max_length=2000)
    lang: str = Field("auto", max_length=8)  # "auto" | "hi" | "en"
    profile: str = Field("", max_length=1500)  # Business Check-up snippet (falls back to session state)


class ChatResponse(BaseModel):
    reply: str
    session_id: str = ""
    history_count: int = 0


class ChatHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]] = []


class ChatDeleteResponse(BaseModel):
    status: str
    session_id: str


# ── sessions (resume) ─────────────────────────────────────────────────────────

class SessionResponse(BaseModel):
    session_id: str
    topic: str = ""
    final_report: str = ""
    simplified_report: str = ""
    updated_at: Optional[float] = None


# ── voice ─────────────────────────────────────────────────────────────────────

class SpeakRequest(BaseModel):
    text: str = Field(..., max_length=5000)


class TranscribeResponse(BaseModel):
    text: str = ""
    warning: Optional[str] = None


class LiveKitTokenRequest(BaseModel):
    topic: str = ""  # optional context — not stored, kept for future room scoping


class LiveKitTokenResponse(BaseModel):
    url: str
    token: str
    room: str
    identity: str


class VoiceStatusResponse(BaseModel):
    """Diagnostics for operators + the frontend voice privacy chip."""

    whisper_model: str = "tiny"
    stt_engines: Dict[str, bool] = {}
    tts_engines: Dict[str, bool] = {}
    stt_default: str = "none"  # elevenlabs | faster_whisper | speech_recognition | none
    tts_default: str = "none"  # elevenlabs | piper | huggingface | pyttsx3 | none
    piper_voices: Dict[str, str] = {}
    private_by_default: bool = True  # True when no API key → local/open-source engines only


# ── langchain / agentic diagnostics ───────────────────────────────────────────

class AgenticStatus(BaseModel):
    langchain_available: bool = False
    langgraph_available: bool = False
    engine: str = "native"
    nodes: List[Dict[str, Any]] = []
    edges: List[List[str]] = []
    tools: List[str] = []


class LangChainStatusResponse(BaseModel):
    available: bool = False
    provider_priority: List[str] = []
    model: str = ""
    tools: List[str] = []
    agentic: AgenticStatus = AgenticStatus()


class LangChainRunRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=4000)
    system_prompt: str = Field(
        default="You are a helpful business advisor for micro-entrepreneurs in India.",
        max_length=2000,
    )
    agent_hint: str = "default"
    temperature: float = 0.7
    max_tokens: int = 500


class LangChainRunResponse(BaseModel):
    reply: str
    via_langchain: bool = False


# ── health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    model: str