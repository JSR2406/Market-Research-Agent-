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
    profile: str = Field("", max_length=1500)
    # Structured Business Check-up answers {field_id: text}. This is the single
    # intake layer shared with the research run; normalize_intake() drops
    # unknown ids and caps every value before it reaches an agent.
    intake: Dict[str, str] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    reply: str
    session_id: str = ""
    history_count: int = 0


class ChatHistoryResponse(BaseModel):
    messages: List[Dict[str, Any]] = []


class ChatDeleteResponse(BaseModel):
    status: str
    session_id: str


# ── sessions (resume + history) ───────────────────────────────────────────────

class SessionResponse(BaseModel):
    session_id: str
    topic: str = ""
    final_report: str = ""
    simplified_report: str = ""
    updated_at: Optional[float] = None


class RunSummary(BaseModel):
    run_id: str
    created_at: float
    topic: str
    has_report: bool
    eligibility: Dict[str, Any] = {}
    loan_ready_score: Optional[int] = None


class RunsListResponse(BaseModel):
    runs: List[RunSummary] = []


class RunDetailResponse(BaseModel):
    session_id: str
    run_id: str
    topic: str = ""
    final_report: str = ""
    simplified_report: str = ""
    eligibility: Dict[str, Any] = {}
    action_ledger: Dict[str, Any] = {}
    # `plan` is the compiled step list (list[str]) in the run state, or a dict in
    # the advisory JSON — accept either so neither shape 500s the endpoint.
    plan: Any = {}
    plan_run: Dict[str, Any] = {}
    intake: Dict[str, str] = {}
    profile: str = ""
    sources: List[Dict[str, Any]] = []
    token_usage: Dict[str, Any] = {}
    engine: str = ""
    created_at: Optional[float] = None


class SessionFactsResponse(BaseModel):
    facts: Dict[str, Any] = {}
    intake: Dict[str, str] = {}


class SessionDeleteResponse(BaseModel):
    """GDPR right-to-delete result."""

    status: str
    session_id: str


class SessionExportResponse(BaseModel):
    """A full, self-contained dump of one session the user owns."""

    session_id: str
    exported_at: float
    topic: str = ""
    run_count: int = 0
    runs: List[Dict[str, Any]] = []
    facts: Dict[str, Any] = {}
    intake: Dict[str, str] = {}
    chat: List[Dict[str, Any]] = []


# ── Eligibility + Action Ledger — deterministic, never LLM-generated ──────────


class EligibilityRequest(BaseModel):
    topic: str = Field("", max_length=2000)
    # Optional explicit loan amount; when absent the engine reads it from the
    # topic only if the message actually mentions borrowing.
    amount: Optional[int] = None
    lang: str = Field("en", max_length=8)  # "en" | "hi" — matches the site language
    intake: Dict[str, str] = Field(default_factory=dict)


class EligibilityResponse(BaseModel):
    business_class: str = ""
    business_label: str = ""
    signals: List[str] = []
    amount: Optional[int] = None
    families: List[Dict[str, Any]] = []
    summary: str = ""
    coverage: Dict[str, Any] = {}
    next_probe: str = ""
    # Question wording in the requested language — response_model is strict, so
    # this field must be declared or FastAPI silently strips it.
    questions: Dict[str, str] = {}


class LedgerTickRequest(BaseModel):
    completed: List[str] = Field(default_factory=list, max_length=40)
    persist: bool = True


class LedgerResponse(BaseModel):
    session_id: str = ""
    score: int = 0
    points_earned: int = 0
    points_possible: int = 100
    reasons: List[str] = []
    next_action: Optional[Dict[str, Any]] = None
    blockers: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    done_count: int = 0
    total_count: int = 0
    completed: List[str] = []


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