"""
backend/api/dpr.py — bank-ready Detailed Project Report (WS-5).

  POST /api/dpr                  build a report, return a job id + the report
  GET  /api/dpr/{job_id}         re-read a report (e.g. after a page reload)
  GET  /api/dpr/{job_id}/pdf     download the report as a PDF

The report itself is deterministic and computed in code (``backend.core.dpr``),
so it finishes in well under a second and no worker queue is needed. The job id
exists for the two things a job id is genuinely good for: fetching the PDF in a
second request, and reporting progress.

**Storage.** Jobs live in memory only, capped and time-limited, so a report is
*not* written to disk by default — the browser downloads the file, which is the
privacy-preserving default. Nothing here survives a restart.
"""
import logging
import time
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Response

from backend.api.schemas import DprJobResponse, DprRequest
from backend.core.dpr import build_dpr, dpr_to_pdf
from backend.core.memory import is_valid_session_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dpr", tags=["dpr"])

_MAX_JOBS = 50
_JOB_TTL_SECONDS = 30 * 60
_JOBS: Dict[str, Dict[str, Any]] = {}


def _evict() -> None:
    """Drop expired jobs, then the oldest ones past the cap."""
    now = time.time()
    for job_id in [j for j, job in _JOBS.items() if now - job["created_at"] > _JOB_TTL_SECONDS]:
        _JOBS.pop(job_id, None)
    while len(_JOBS) > _MAX_JOBS:
        oldest = min(_JOBS, key=lambda j: _JOBS[j]["created_at"])
        _JOBS.pop(oldest, None)


def _clean_session_id(session_id: str) -> str:
    value = (session_id or "").strip()
    if not value:
        return ""
    return value if is_valid_session_id(value) else ""


@router.post("", response_model=DprJobResponse)
async def create_dpr(req: DprRequest):
    """Build the report now and return it with a job id for the PDF fetch."""
    session_id = _clean_session_id(req.session_id)
    try:
        report = build_dpr(
            req.intake,
            req.topic,
            req.scheme_id or None,
            req.project_cost,
            req.monthly_sales,
            req.monthly_expenses,
            session_id or None,
            req.lang,
        )
        # The PDF is always rendered from an English build: a PDF needs an
        # embedded Devanagari font and text shaping, which this dependency-free
        # writer does not do — and banks read English files anyway. The on-screen
        # report is localised.
        pdf_source = report if req.lang != "hi" else build_dpr(
            req.intake,
            req.topic,
            req.scheme_id or None,
            req.project_cost,
            req.monthly_sales,
            req.monthly_expenses,
            session_id or None,
            "en",
        )
        pdf_bytes = dpr_to_pdf(pdf_source)
    except Exception:  # a report request must never 500
        logger.exception("[dpr] report build failed")
        return DprJobResponse(
            status="error",
            error="Could not build the report right now. Please try again.",
        )

    job_id = uuid.uuid4().hex
    _evict()
    _JOBS[job_id] = {
        "created_at": time.time(),
        "report": report,
        "pdf": pdf_bytes,
        "pdf_language": "en",
    }
    return DprJobResponse(
        job_id=job_id,
        status="done",
        progress=[
            "Collected your answers",
            "Computed the three-year projection and DSCR",
            "Attached the scheme's document checklist",
            "Rendered the PDF",
        ],
        report=report,
        pdf_url=f"/api/dpr/{job_id}/pdf",
    )


def _job_or_404(job_id: str) -> Dict[str, Any]:
    job = _JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="That report has expired. Please generate it again.")
    return job


@router.get("/{job_id}", response_model=DprJobResponse)
async def get_dpr(job_id: str):
    job = _job_or_404(job_id)
    return DprJobResponse(
        job_id=job_id,
        status="done",
        progress=["Report ready"],
        report=job["report"],
        pdf_url=f"/api/dpr/{job_id}/pdf",
    )


@router.get("/{job_id}/pdf")
async def get_dpr_pdf(job_id: str):
    job = _job_or_404(job_id)
    filename = (job["report"].get("meta") or {}).get("scheme_id") or "business"
    return Response(
        content=job["pdf"],
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="dpr-{filename}.pdf"'},
    )
