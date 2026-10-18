"""
backend/api/advisor.py — advisor / CA workspace API (WS-11).

All routes live under ``/api/advisor/*`` and are guarded by a bearer session
token (``Authorization: Bearer <token>``). A bearer header is used instead of
a cookie because the app is deployed cross-origin (frontend on Vercel,
backend on Render); cookies would not survive that boundary. The real
security property — **advisor isolation** — is enforced in the repository
layer (``backend.core.advisor``), which injects ``advisorId`` into every
query, so advisor A can never read, update or delete advisor B's records.

Eligibility, benefit and document logic reuse the WS-2 / WS-3 engines
unchanged — nothing is forked, so results are deterministic and offline.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

import os

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import FileResponse

from backend.api.schemas import (
    AdvisorLoginRequest,
    AdvisorLoginResponse,
    AdvisorSignupRequest,
    AdvisorSignupResponse,
    AuthMeResponse,
    BulkMatchRequest,
    BulkMatchResponse,
    ClientListResponse,
    ClientProfile,
    ClientResponse,
    ClientUpdateRequest,
    MatchRequest,
    MatchResponse,
    NoteListResponse,
    NoteRequest,
    NoteResponse,
    ReportListResponse,
    ReportRequest,
    ReportResponse,
)
from backend.core import advisor as advisor_repo
from backend.core.advisor import ENGINE_VERSION, MAX_BATCH
from backend.core.analytics import record_events
from backend.core.benefits import compute_benefits
from backend.core.eligibility import evaluate_schemes
from backend.core.heuristics import load_schemes  # schemes.json registry
from backend.core.pdf import render_pdf

import time as _time

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/advisor", tags=["advisor"])

REPORTS_DIR = advisor_repo.ADVISOR_DIR / "reports"


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

def get_current_advisor(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Validate the bearer token; return the safe advisor dict or raise 401."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Sign in to open the advisor workspace.")
    token = authorization.split(" ", 1)[1].strip()
    advisor = advisor_repo.get_session(token)
    if not advisor:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Sign in again.")
    return advisor


@router.post("/auth/signup", response_model=AdvisorSignupResponse)
async def advisor_signup(req: AdvisorSignupRequest):
    """Create an advisor account (email + password)."""
    advisor = advisor_repo.create_advisor(
        email=req.email,
        password=req.password,
        name=req.name,
        org_name=req.org_name or None,
    )
    if not advisor:
        raise HTTPException(status_code=422, detail="An account with that email already exists.")
    record_events([{"name": "advisor_signed_up", "props": {"plan": advisor.get("plan", "free")}}])
    return AdvisorSignupResponse(
        id=advisor["id"], email=advisor["email"], name=advisor["name"], locale=advisor["locale"]
    )


@router.post("/auth/login", response_model=AdvisorLoginResponse)
async def advisor_login(req: AdvisorLoginRequest):
    """Sign in; returns a bearer token the frontend stores and re-sends."""
    advisor = advisor_repo.authenticate_advisor(req.email, req.password)
    if not advisor:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = advisor_repo.create_session(advisor["id"])
    if not token:
        raise HTTPException(status_code=500, detail="Could not start a session.")
    record_events([{"name": "advisor_signed_in", "props": {}}])
    return AdvisorLoginResponse(
        id=advisor["id"], email=advisor["email"], name=advisor["name"], locale=advisor["locale"],
        token=token,
    )


@router.post("/auth/logout")
async def advisor_logout(authorization: Optional[str] = Header(None)):
    """Revoke the current session."""
    if authorization and authorization.lower().startswith("bearer "):
        advisor_repo.delete_session(authorization.split(" ", 1)[1].strip())
    return {"status": "logged out"}


@router.get("/auth/me", response_model=AuthMeResponse)
async def advisor_me(advisor: Dict[str, Any] = Depends(get_current_advisor)):
    """Return the signed-in advisor's public profile."""
    return AuthMeResponse(
        id=advisor["id"], email=advisor["email"], name=advisor.get("name", ""),
        org_name=advisor.get("org_name", ""), locale=advisor.get("locale", "en"),
        plan=advisor.get("plan", "free"),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Clients
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/clients", response_model=ClientListResponse)
async def list_clients(
    advisor: Dict[str, Any] = Depends(get_current_advisor),
    q: Optional[str] = Query(None, max_length=200),
    sector: Optional[str] = Query(None, max_length=64),
    state: Optional[str] = Query(None, max_length=64),
    stage: Optional[str] = Query(None, max_length=32),
    readiness: Optional[str] = Query(None, max_length=16),
):
    """List this advisor's clients, with optional search + filters."""
    clients = advisor_repo.list_clients(advisor["id"])
    ql = (q or "").strip().lower()
    filtered = []
    for c in clients:
        label = (c.get("label") or "").lower()
        if ql and ql not in label:
            continue
        if sector and (c.get("sector") or "") != sector:
            continue
        if state and (c.get("state") or "") != state:
            continue
        if stage and (c.get("stage") or "") != stage:
            continue
        if readiness:
            r = c.get("readiness")
            if r is None:
                continue
            if readiness == "high" and r < 70:
                continue
            if readiness == "medium" and not (40 <= r < 70):
                continue
            if readiness == "low" and r >= 40:
                continue
        filtered.append(c)
    return ClientListResponse(clients=filtered)


@router.post("/clients", response_model=ClientResponse)
async def create_client(req: ClientProfile, advisor: Dict[str, Any] = Depends(get_current_advisor)):
    """Add a managed client profile (same fields as the WS-2 check-up)."""
    client = advisor_repo.create_client(
        advisor["id"], label=req.label, profile=req.profile,
        sector=req.sector or None, state=req.state or None, stage=req.stage or None,
    )
    if not client:
        raise HTTPException(status_code=422, detail="Could not create the client.")
    record_events([{
        "name": "advisor_client_added", "props": {"count": 1},
    }])
    return ClientResponse(**client)


@router.get("/clients/{client_id}", response_model=ClientResponse)
async def get_client(
    client_id: str, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    """One client: profile, latest eligibility snapshot and notes."""
    client = advisor_repo.get_client(advisor["id"], client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    snapshot = advisor_repo.get_latest_snapshot(advisor["id"], client_id)
    if snapshot:
        client["readiness"] = snapshot["results"].get("readiness") or client.get("readiness")
    return ClientResponse(**client)


@router.patch("/clients/{client_id}", response_model=ClientResponse)
async def update_client(
    client_id: str, req: ClientUpdateRequest, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    client = advisor_repo.update_client(
        advisor["id"], client_id,
        label=req.label, profile=req.profile,
        sector=req.sector, state=req.state, stage=req.stage,
    )
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    record_events([{"name": "advisor_client_updated", "props": {}}])
    return ClientResponse(**client)


@router.delete("/clients/{client_id}")
async def delete_client(
    client_id: str, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    """Delete a client and cascade its notes + snapshots (GDPR hard delete)."""
    ok = advisor_repo.delete_client_cascade(advisor["id"], client_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Client not found.")
    record_events([{"name": "advisor_client_deleted", "props": {}}])
    return {"status": "deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# Eligibility (single client + bulk) — reuses the WS-2 engine unchanged
# ─────────────────────────────────────────────────────────────────────────────

def _client_intake(client: Dict[str, Any]) -> Dict[str, str]:
    """Merge the stored profile with any explicit intake overrides."""
    profile = client.get("profile") or {}
    intake: Dict[str, str] = {}
    for k, v in profile.items():
        if isinstance(v, str) and v.strip():
            intake[k] = v.strip()
    return intake


@router.post("/clients/{client_id}/match", response_model=MatchResponse)
async def match_client(
    client_id: str, req: MatchRequest, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    """Run eligibility for one client and store a reproducible snapshot."""
    client = advisor_repo.get_client(advisor["id"], client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")

    intake = dict(_client_intake(client))
    for k, v in (req.intake or {}).items():
        if isinstance(v, str) and v.strip():
            intake[k] = v.strip()

    result = evaluate_schemes(
        intake=intake, topic=req.topic, amount=req.amount, lang=req.lang,
    )
    snapshot = advisor_repo.save_snapshot(
        advisor["id"], client_id, ENGINE_VERSION, result,
    )
    ranked = result.get("ranked") or []
    return MatchResponse(
        client_id=client_id, label=client.get("label", ""),
        readiness=client.get("readiness"),
        business_class=result.get("business_class", ""),
        business_label=result.get("business_label", ""),
        ranked=ranked,
        snapshot_id=snapshot["id"] if snapshot else "",
    )


@router.post("/eligibility/bulk", response_model=BulkMatchResponse)
async def bulk_match(
    req: BulkMatchRequest, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    """Run eligibility for many clients in one pass; unowned ids are silently dropped."""
    client_ids = list(dict.fromkeys(req.client_ids or []))[:MAX_BATCH]
    results: List[Dict[str, Any]] = []
    for client_id in client_ids:
        client = advisor_repo.get_client(advisor["id"], client_id)
        if not client:
            # Not owned by this advisor — omit (do not leak existence).
            logger.warning("[advisor] bulk match: advisor %s requested unowned client %s",
                           advisor["id"], client_id)
            continue
        intake = _client_intake(client)
        result = evaluate_schemes(intake=intake, topic="", amount=None, lang="en")
        snapshot = advisor_repo.save_snapshot(
            advisor["id"], client_id, ENGINE_VERSION, result,
        )
        ranked = result.get("ranked") or []
        results.append({
            "client_id": client_id,
            "label": client.get("label", ""),
            "readiness": client.get("readiness"),
            "matches": [
                {
                    "scheme_slug": m.get("scheme_id", ""),
                    "score": m.get("score", 0),
                    "eligible": m.get("status") in ("eligible", "likely"),
                    "reasons": [r.get("label", "") for r in (m.get("matched") or [])],
                }
                for m in ranked[:5]
            ],
        })
    record_events([{
        "name": "bulk_match_run", "props": {"clientCount": len(results)},
    }])
    return BulkMatchResponse(results=results)


# ─────────────────────────────────────────────────────────────────────────────
# Notes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/clients/{client_id}/notes", response_model=NoteListResponse)
async def list_notes(
    client_id: str, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    client = advisor_repo.get_client(advisor["id"], client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    return NoteListResponse(notes=advisor_repo.list_notes(advisor["id"], client_id))


@router.post("/clients/{client_id}/notes", response_model=NoteResponse)
async def add_note(
    client_id: str, req: NoteRequest, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    client = advisor_repo.get_client(advisor["id"], client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found.")
    note = advisor_repo.add_note(advisor["id"], client_id, req.body)
    if not note:
        raise HTTPException(status_code=422, detail="Could not save the note.")
    record_events([{"name": "advisor_note_added", "props": {}}])
    return NoteResponse(**note)


@router.delete("/notes/{note_id}")
async def delete_note(
    note_id: str, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    ok = advisor_repo.delete_note(advisor["id"], note_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Note not found.")
    return {"status": "deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# Reports (combined + single-client PDF)
# ─────────────────────────────────────────────────────────────────────────────

def _scheme_source_line(scheme: Dict[str, Any], lang: str) -> str:
    name = scheme.get("name", "")
    url = scheme.get("source_url", "")
    verified = scheme.get("last_verified_at", "")
    return f"{name} (source: {url}, verified {verified})" if url else name


def _build_pdf_blocks(advisor: Dict[str, Any], client_summaries: List[Dict[str, Any]],
                      locale: str, kind: str) -> List[Dict[str, str]]:
    """Assemble the report's text blocks (English — see pdf.py Latin-1 limit)."""
    blocks: List[Dict[str, str]] = []
    org = advisor.get("org_name") or advisor.get("name") or "Advisor"
    blocks.append({"style": "h1", "text": "Your AI Business Saathi — Advisor Report"})
    blocks.append({"style": "body", "text": f"Advisor: {org}"})
    blocks.append({"style": "body", "text": f"Generated: {date.today().isoformat()}"})
    blocks.append({"style": "body", "text": f"Report type: {kind}"})
    blocks.append({"style": "body", "text": f"Locale: {locale}"})
    blocks.append({"style": "body", "text": ""})
    blocks.append({
        "style": "body",
        "text": ("Independent platform, not affiliated with or endorsed by the Government of "
                 "India or any state government. Guidance only, not a lending decision."),
    })
    blocks.append({"style": "body", "text": ""})

    for summary in client_summaries:
        blocks.append({"style": "h2", "text": summary.get("label", "Client")})
        blocks.append({"style": "body", "text": f"Business type: {summary.get('business_label', '—')}"})
        blocks.append({"style": "body", "text": f"Readiness score: {summary.get('readiness', 0)} / 100"})
        blocks.append({"style": "body", "text": ""})
        blocks.append({"style": "h3", "text": "Matched schemes"})
        for m in summary.get("matches", [])[:6]:
            blocks.append({
                "style": "bullet",
                "text": f"{m.get('name', m.get('scheme_slug',''))} — score {m.get('score', 0)} "
                        f"({m.get('status','')})",
            })
            for reason in (m.get("reasons") or [])[:3]:
                blocks.append({"style": "bullet", "text": f"  • {reason}"})
        blocks.append({"style": "body", "text": ""})
        blocks.append({"style": "h3", "text": "Documents needed"})
        for doc in (summary.get("documents") or [])[:6]:
            blocks.append({"style": "bullet", "text": str(doc)})
        blocks.append({"style": "body", "text": ""})
        blocks.append({"style": "h3", "text": "Scheme sources"})
        for line in summary.get("source_lines", [])[:6]:
            blocks.append({"style": "bullet", "text": line})

    return blocks


@router.post("/reports", response_model=ReportResponse)
async def generate_report(
    req: ReportRequest, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    """Generate a combined or single-client PDF report (synchronous for MVP)."""
    if req.kind not in ("combined", "single"):
        raise HTTPException(status_code=422, detail="kind must be 'combined' or 'single'.")
    client_ids = list(req.client_ids or [])
    if not client_ids:
        raise HTTPException(status_code=422, detail="Select at least one client.")

    summaries: List[Dict[str, Any]] = []
    for client_id in client_ids:
        client = advisor_repo.get_client(advisor["id"], client_id)
        if not client:
            continue
        snapshot = advisor_repo.get_latest_snapshot(advisor["id"], client_id)
        result = snapshot["results"] if snapshot else evaluate_schemes(
            intake=_client_intake(client), topic="", amount=None, lang=req.locale,
        )
        ranked = result.get("ranked", [])
        matches = []
        documents: List[str] = []
        source_lines: List[str] = []
        schemes = {s.get("id"): s for s in load_schemes()}
        for m in ranked:
            scheme = schemes.get(m.get("scheme_id", ""), {})
            matches.append({
                "name": m.get("name", ""),
                "scheme_slug": m.get("scheme_id", ""),
                "score": m.get("score", 0),
                "status": m.get("status", ""),
                "reasons": [r.get("label", "") for r in (m.get("matched") or [])],
            })
            documents.extend(m.get("documents", []) or [])
            source_lines.append(_scheme_source_line(scheme, req.locale))
        benefit = compute_benefits(
            intake=_client_intake(client), topic="", amount=None, project_cost=None, lang=req.locale,
        )
        summaries.append({
            "label": client.get("label", ""),
            "business_label": result.get("business_label", ""),
            "readiness": client.get("readiness") or (max((m.get("score", 0) for m in ranked), default=0) if ranked else 0),
            "matches": matches,
            "documents": list(dict.fromkeys(documents))[:8],
            "source_lines": source_lines,
            "benefit_headline": benefit.get("headline", {}),
        })

    blocks = _build_pdf_blocks(advisor, summaries, req.locale, req.kind)
    pdf_bytes = render_pdf(
        title="Advisor Report",
        blocks=blocks,
        footer=("Independent platform, not affiliated with or endorsed by the Government of India "
                "or any state government. Guidance only, not a lending decision."),
    )
    _init_reports_dir()
    file_name = f"advisor_report_{advisor['id']}_{int(_time.time())}.pdf"
    file_path = str(REPORTS_DIR / file_name)
    REPORTS_DIR.joinpath(file_name).write_bytes(pdf_bytes)

    report = advisor_repo.create_report(
        advisor["id"], kind=req.kind, client_ids=client_ids, locale=req.locale, file_path=file_path,
    )
    if not report:
        raise HTTPException(status_code=500, detail="Could not record the report.")
    record_events([{
        "name": "advisor_report_generated", "props": {"kind": req.kind, "locale": req.locale},
    }])
    return ReportResponse(**report)


@router.get("/reports", response_model=ReportListResponse)
async def list_reports(advisor: Dict[str, Any] = Depends(get_current_advisor)):
    return ReportListResponse(
        reports=[ReportResponse(**r) for r in advisor_repo.list_reports(advisor["id"])]
    )


@router.get("/reports/{report_id}")
async def get_report(
    report_id: str, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    report = advisor_repo.get_report(advisor["id"], report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return {"report": report, "pdf_url": f"/api/advisor/reports/{report_id}/pdf"}


@router.get("/reports/{report_id}/pdf")
async def download_report_pdf(
    report_id: str, advisor: Dict[str, Any] = Depends(get_current_advisor),
):
    report = advisor_repo.get_report(advisor["id"], report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    file_path = report.get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Report file not found.")
    return FileResponse(
        file_path, media_type="application/pdf",
        filename=f"advisor-report-{report_id}.pdf",
    )


def _init_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
