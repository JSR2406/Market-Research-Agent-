import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.ws_market import router as ws_router

app = FastAPI(title="Market Research Agent")

# ── CORS ──────────────────────────────────────────────────────────
# Allow localhost in dev + any production frontend via env var.
# Set ALLOWED_ORIGINS in your backend host (Railway/Render/Fly) as a
# comma-separated list, e.g.:
#   ALLOWED_ORIGINS=https://market-research-agent-jsr2406.vercel.app
_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:3001",
)
ALLOWED_ORIGINS: list[str] = [o.strip() for o in _raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ws_router)


@app.get("/health")
async def health():
    return {"status": "ok", "allowed_origins": ALLOWED_ORIGINS}
