import asyncio
import concurrent.futures
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    # LangGraph is optional at runtime, but the project routes its orchestration
    # through it when available. Import failures should not crash the app boot.
    from langgraph.graph import END, START, StateGraph  # type: ignore
    LANGGRAPH_AVAILABLE = True
    LANGGRAPH_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on env
    END = START = StateGraph = None  # type: ignore
    LANGGRAPH_AVAILABLE = False
    LANGGRAPH_IMPORT_ERROR = str(exc)
    logger.warning("[runtime] LangGraph unavailable: %s", exc)


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
    return "langgraph" if LANGGRAPH_AVAILABLE else "native"
