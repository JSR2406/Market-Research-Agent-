import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# config.py exits immediately if OPENROUTER_API_KEY is missing while "openrouter"
# is in the provider priority — this surfaces the error before uvicorn starts.
from backend.core import config  # noqa: F401  (import for side-effect / fail-fast)
from backend.core.config import ALLOWED_ORIGINS
from backend.api.schemas import HealthResponse
from backend.api.ledger import router as ledger_router
from backend.api.benefits import router as benefits_router
from backend.api.documents import router as documents_router
from backend.api.dpr import router as dpr_router
from backend.api.schemes import router as schemes_router
from backend.api.analytics import router as analytics_router
from backend.api.voice import router as voice_router
from backend.api.chat import router as chat_router
from backend.api.sessions import router as sessions_router
from backend.api.langchain import router as langchain_router
from backend.api.whatsapp import router as whatsapp_router
from backend.api.ws_market import router as ws_router
from backend.core.memory import cleanup_old_sessions
from backend.core.analytics import cleanup_analytics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        f"Market Research Agent started | model={config.MODEL} | "
        f"origins={ALLOWED_ORIGINS}"
    )
    # Session retention cleanup: auto-delete stale sessions older than 7 days.
    try:
        deleted = cleanup_old_sessions()
        if deleted:
            logger.info(f"[Memory] Retention cleanup: removed {deleted} expired session(s).")
    except Exception as e:
        logger.error(f"[Memory] Retention cleanup failed: {e}")
    # Analytics retention: daily event files are pruned after 30 days.
    try:
        removed = cleanup_analytics()
        if removed:
            logger.info(f"[Analytics] Retention cleanup: removed {removed} expired file(s).")
    except Exception as e:
        logger.error(f"[Analytics] Retention cleanup failed: {e}")
    yield


def _register_exception_handlers(app: FastAPI) -> None:
    """
    Unified, friendly JSON error contract (P0): the client never sees Python
    details or stack traces — internals go to server logs only.

    - Invalid input (422) → one generic human message.
    - Any uncaught exception → generic 500 JSON, details logged.
    - FastAPI's default HTTPException handler is left intact (it already
      returns a clean {"detail": ...}).
    """

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        logger.warning("[API] 422 %s: %s", request.url.path, exc.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": "Some input was not valid. Please check and try again."},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("[API] unhandled error on %s: %s", request.url.path, exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Something went wrong on our side. Please try again."},
        )


app = FastAPI(title="Market Research Agent", lifespan=lifespan)

_register_exception_handlers(app)


@app.middleware("http")
async def _log_http(request: Request, call_next):
    """
    Observability: per-request structured log line (method, path, status, ms).
    Path only — never query strings, bodies, or headers, so no PII leaks into logs.
    Exceptions raised inside call_next fall through to the global 500 handler,
    which logs the full trace instead.
    """
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "[http] %s %s -> %s (%d ms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)
app.include_router(voice_router)
app.include_router(chat_router)
app.include_router(sessions_router)
app.include_router(langchain_router)
app.include_router(whatsapp_router)
app.include_router(ledger_router)
app.include_router(benefits_router)
app.include_router(documents_router)
app.include_router(dpr_router)
app.include_router(schemes_router)
app.include_router(analytics_router)


@app.get("/health", response_model=HealthResponse)
async def health():
    # Deliberately minimal — do not echo config/origins to the public internet.
    return {
        "status": "ok",
        "model": config.MODEL,
    }