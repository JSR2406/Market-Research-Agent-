"""
backend/api/documents.py — per-scheme document checklist (WS-4).

  POST /api/documents    grouped, per-scheme document list + share text

Computed in code from the curated ``documents`` lists in ``schemes.json``; the
endpoint is pure and offline, so it keeps answering with every model provider
down. Input ids are validated against the dataset — unknown ids are ignored
rather than echoed back.
"""
import logging

from fastapi import APIRouter

from backend.api.schemas import DocumentPlanResponse, DocumentRequest
from backend.core.documents import build_document_plan

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("", response_model=DocumentPlanResponse)
async def documents(req: DocumentRequest):
    """Checklists for the schemes that match (or the ids the caller names)."""
    try:
        return build_document_plan(
            req.intake,
            req.topic,
            req.scheme_ids,
            req.lang,
        )
    except Exception:  # a checklist must never 500
        logger.exception("[documents] checklist build failed")
        return DocumentPlanResponse(
            disclaimer="Could not build the checklist right now. Please check the scheme's official page."
        )
