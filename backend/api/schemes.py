"""
backend/api/schemes.py — read-only access to the curated scheme dataset.

  GET /api/schemes        every scheme, with its source + verified date

This is the *official data* half of the product exposed on its own: the Scheme
Explorer page browses exactly what the rule engine reasons about, so what a user
reads here and what they are told they qualify for can never disagree.

Nothing here is generated. Each record is served verbatim from
``backend/data/schemes.json`` (which carries ``source_url`` and
``last_verified_at`` per entry), so the page can always show provenance.
"""
import logging
from typing import Any, Dict, List

from fastapi import APIRouter
from pydantic import BaseModel

from backend.core.heuristics import load_schemes
from backend.core.provenance import annotate_schemes, staleness_report

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/schemes", tags=["schemes"])


class SchemesResponse(BaseModel):
    schemes: List[Dict[str, Any]] = []
    count: int = 0


class SchemesHealthResponse(BaseModel):
    """Whole-dataset freshness summary (WS-7) — provenance as a worklist."""

    total: int = 0
    fresh: int = 0
    stale: List[str] = []
    due_soon: List[str] = []
    unsourced: List[str] = []
    unknown: List[str] = []
    cadence_days: int = 0
    generated_at: str = ""


@router.get("/health", response_model=SchemesHealthResponse)
async def schemes_health():
    """Freshness of every curated record — which schemes need re-verification.

    Deterministic and offline-safe: it reads ``last_verified_at`` and compares it
    to a fixed cadence. Register this route *before* the catch-all ``""`` route so
    ``/api/schemes/health`` is not swallowed by a path parameter (there is none,
    but ordering keeps the intent explicit).
    """
    return staleness_report(load_schemes())


@router.get("", response_model=SchemesResponse)
@router.get("/list", response_model=SchemesResponse)
async def list_schemes():
    """Return the full curated scheme dataset (safe, public scheme metadata).

    Mounted on both ``/api/schemes`` and ``/api/schemes/list`` so the API reads
    naturally either way; the data is identical. Each record is annotated with a
    ``provenance`` block (source host, verified date, review window) so the UI can
    show how current it is without re-deriving anything.
    """
    schemes = annotate_schemes(load_schemes())
    return {"schemes": schemes, "count": len(schemes)}
