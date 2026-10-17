"""
backend/api/analytics.py — first-party usage analytics (WS-12).

    POST /api/analytics/events    record a batch of allowlisted events
    GET  /api/analytics/summary   aggregate counts + funnel over a window

Both endpoints are aggregate-only and store nothing but named event counts under
an anonymous session id (see ``backend/core/analytics.py``). They are local,
network-free, and never raise: a malformed analytics request must not be able to
surface an error to the user or disturb a research run.
"""
import logging

from fastapi import APIRouter, Query

from backend.api.schemas import (
    AnalyticsBatchRequest,
    AnalyticsBatchResponse,
    AnalyticsSummaryResponse,
)
from backend.core.analytics import record_events, summarize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.post("/events", response_model=AnalyticsBatchResponse)
async def record(payload: AnalyticsBatchRequest):
    """Store sanitised events. Unknown names are dropped, never stored.

    Returns 200 with ``accepted``/``rejected`` counts rather than a 4xx: the
    client sends these fire-and-forget, and a rejected event is a normal
    (expected) outcome, not an error the user should ever see.
    """
    events = [event.model_dump() for event in payload.events]
    result = record_events(events, payload.session_id)
    return result


@router.get("/summary", response_model=AnalyticsSummaryResponse)
async def summary(days: int = Query(default=7, ge=1, le=30)):
    """Aggregate event counts and the check-up → research funnel."""
    return summarize(days)
