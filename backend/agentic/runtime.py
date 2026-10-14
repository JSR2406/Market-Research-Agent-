"""
backend/agentic/runtime.py — availability flags and small execution helpers.

Keeps the "is LangGraph/LangChain installed?" question in exactly one place and
provides a safe sync→async bridge for the few tools that are called from sync
contexts. Import of this module must never fail because a heavy optional
dependency is missing.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── optional dependency detection ───────────────────────────────────────────
try:  # langgraph is the primary orchestrator when present
    import langgraph  # noqa: F401
    from langgraph.graph import END, START, StateGraph

    LANGGRAPH_AVAILABLE = True
    LANGGRAPH_IMPORT_ERROR: Optional[str] = None
except Exception as e:  # pragma: no cover — native runner takes over
    LANGGRAPH_AVAILABLE = False
    LANGGRAPH_IMPORT_ERROR = str(e)
    logger.info("[Agentic] LangGraph unavailable, native graph runner will be used: %s", e)

try:
    import langchain_core  # noqa: F401

    LANGCHAIN_CORE_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGCHAIN_CORE_AVAILABLE = False

try:
    import langchain  # noqa: F401

    LANGCHAIN_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGCHAIN_AVAILABLE = False


def run_coro_sync(coro):
    """Run an async coroutine from sync code, even inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # Already inside a loop — isolate on a new loop in a worker thread.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def engine_name() -> str:
    """Human-readable name of the engine that will actually execute the graph."""
    return "langgraph" if LANGGRAPH_AVAILABLE else "native"
