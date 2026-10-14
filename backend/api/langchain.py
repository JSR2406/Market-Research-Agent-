"""
backend/api/langchain.py — optional LangChain-powered endpoint.

Endpoints:
- GET  /api/langchain/status  availability + model info (never requires langchain)
- POST /api/langchain/run     run a prompt through the LangChain advisory chain

All LLM traffic flows through backend/core/llm_client.call_llm (via the
GrameenChatModel adapter). Every response carries a heuristic fallback, so the
endpoint never returns a hard 500.
"""
import logging

from fastapi import APIRouter

from backend.api.schemas import (
    LangChainRunRequest,
    LangChainRunResponse,
    LangChainStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/langchain", tags=["langchain"])


@router.get("/status", response_model=LangChainStatusResponse)
async def langchain_status():
    from backend.core import config
    from backend.core.langchain_adapter import (
        ADVISORY_TOOLS,
        LANGCHAIN_AVAILABLE,
        agentic_status,
    )

    return {
        "available": LANGCHAIN_AVAILABLE,
        "provider_priority": config.LLM_PROVIDER_PRIORITY,
        "model": config.MODEL,
        "tools": [getattr(t, "name", str(t)) for t in ADVISORY_TOOLS],
        "agentic": agentic_status(),
    }


@router.post("/run", response_model=LangChainRunResponse)
async def langchain_run(body: LangChainRunRequest):
    from backend.core.langchain_adapter import (
        LANGCHAIN_AVAILABLE,
        build_advisory_chain,
        run_prompt,
    )

    chain = None
    if LANGCHAIN_AVAILABLE:
        try:
            chain = build_advisory_chain(
                body.system_prompt,
                agent_hint=body.agent_hint,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            )
        except Exception as e:
            logger.warning(f"[LangChain] build_advisory_chain failed: {e}")
            chain = None

    reply = await run_prompt(
        chain,
        body.input,
        agent_hint=body.agent_hint,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
        max_tokens=body.max_tokens,
    )
    return {"reply": reply, "via_langchain": bool(chain is not None)}
