"""
backend/agentic/runtime.py — langgraph availability and execution helpers.

langgraph is a REQUIRED dependency. The LangGraph StateGraph is the sole
execution engine for the agentic advisory pipeline.
"""

import asyncio
import concurrent.futures
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# langgraph is required — always available
from langgraph.graph import END, START, StateGraph  # noqa: F401

LANGGRAPH_AVAILABLE = True
LANGGRAPH_IMPORT_ERROR: Optional[str] = None


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
    """Human-readable name of the engine that executes the graph."""
    return "langgraph"
