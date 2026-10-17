"""
backend/api/benefits.py — deterministic benefit / subsidy calculator (WS-3).

  POST /api/benefits    what a business could get, in rupees

Sits beside ``/api/eligibility``: eligibility says *whether* a scheme is open,
this says *how much*. Everything is computed in code from ``schemes.json``
(``benefit_rules`` + tier bands) plus the user's own answers — no model is
involved, so the endpoint answers identically with every provider offline.
"""
import logging

from fastapi import APIRouter

from backend.api.schemas import BenefitRequest, BenefitResponse
from backend.core.benefits import compute_benefits

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/benefits", tags=["benefits"])


@router.post("", response_model=BenefitResponse)
async def benefits(req: BenefitRequest):
    """Benefit estimates for one business. Never raises on user input.

    Inputs are capped by pydantic (422 on nonsense); the calculation itself is
    pure and offline, so an LLM or network outage cannot degrade it.
    """
    try:
        return compute_benefits(
            req.intake,
            req.topic,
            req.amount,
            req.project_cost,
            req.lang,
        )
    except Exception:  # never 500 on a calculator — log, then an empty answer
        logger.exception("[benefits] calculation failed")
        return BenefitResponse(
            disclaimer=(
                "Could not estimate right now. Please check the scheme's official "
                "page for the current amounts."
            )
        )
