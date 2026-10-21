"""
backend/agentic/events.py — agentic event emitter.

Every node reports progress through an :class:`EventEmitter` bound to the
connection's SafeWebSocket. Both graph runners (LangGraph and the built-in
native one) use the *same* emitter, so the frontend sees an identical real-time
event stream regardless of which engine executed the graph.

Event types (additive to the legacy plan/step_start/step_end/token_usage/
status/done contract):

    status        {message}
    graph         {engine, nodes:[{id,label}], edges:[[from,to]]}
    plan          {topic, plan}
    node_start    {node, label, index, iteration, icon}
    node_end      {node, label, index, summary, output, ok}
    thought       {node, text}
    tool_call     {node, tool, input}
    tool_result   {node, tool, summary, ok}
    reflection    {node, text, action}
    token_usage   {input_tokens, output_tokens, total_tokens}
    gate_pending  {gate}
    gate_decided  {gate}
    done          {topic, final_report, simplified_report, token_usage, trace, engine}

The emitter also keeps an in-memory trace so the final ``done`` event can carry
the whole agentic story for the UI.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class WorkflowCancelled(Exception):
    """Raised (or detected) when the user cancels a run."""


class GatePaused(Exception):
    """
    Raised when a run stops at an approval gate.

    The gate travels with the exception so the caller can tell the user what is
    waiting. ``status`` is ``pending`` (nobody answered yet — the run parked)
    or ``rejected`` (the user said no — the run ends on purpose).
    """

    def __init__(self, gate: Dict[str, Any], status: str = "pending") -> None:
        super().__init__(f"gate {gate.get('gate_id', '?')} is waiting for a decision")
        self.gate = gate
        self.status = status


class EventEmitter:
    """Serialized, best-effort event sink for the agentic graph.

    Never raises on send failure — a dropped socket must not kill the run, and
    the workflow persists its result at the end regardless.
    """

    def __init__(self, websocket: Any, cancel_flag: Optional[dict] = None) -> None:
        self._ws = websocket
        self.cancel_flag = cancel_flag if cancel_flag is not None else {"cancelled": False}
        self._trace: List[Dict[str, Any]] = []
        self._index = 0
        self._token_getter = None

    # ── plumbing ────────────────────────────────────────────────────────────
    def set_token_usage_getter(self, getter) -> None:
        """Attach a callable returning the current SESSION_TOKEN_USAGE dict."""
        self._token_getter = getter

    @property
    def is_cancelled(self) -> bool:
        return bool(self.cancel_flag.get("cancelled"))

    @property
    def trace(self) -> List[Dict[str, Any]]:
        return list(self._trace)

    async def send(self, payload: Dict[str, Any]) -> None:
        try:
            await self._ws.send_json(payload)
        except Exception as e:  # pragma: no cover — socket already gone
            logger.debug("EventEmitter send failed (ignored): %s", e)

    # ── high-level events ───────────────────────────────────────────────────
    async def status(self, message: str) -> None:
        await self.send({"type": "status", "message": message})

    async def graph(self, engine: str, nodes: List[Dict[str, str]], edges: List[List[str]]) -> None:
        await self.send({"type": "graph", "engine": engine, "nodes": nodes, "edges": edges})

    async def plan(self, topic: str, plan: List[str]) -> None:
        await self.send({"type": "plan", "topic": topic, "plan": plan})

    async def node_start(self, node: str, label: str, iteration: int = 0, icon: str = "") -> int:
        idx = self._index
        self._index += 1
        await self.send({
            "type": "node_start",
            "node": node,
            "label": label,
            "icon": icon,
            "index": idx,
            "iteration": iteration,
        })
        return idx

    async def node_end(
        self,
        node: str,
        label: str,
        index: int,
        summary: str = "",
        output: Optional[str] = None,
        ok: bool = True,
        iteration: int = 0,
    ) -> None:
        await self.send({
            "type": "node_end",
            "node": node,
            "label": label,
            "index": index,
            "iteration": iteration,
            "summary": summary,
            "output": output,
            "ok": ok,
        })
        self._record({"node": node, "kind": "note", "text": summary, "ok": ok})

    async def thought(self, node: str, text: str) -> None:
        if not text:
            return
        self._record({"node": node, "kind": "thought", "text": text})
        await self.send({"type": "thought", "node": node, "text": text})

    async def tool_call(self, node: str, tool: str, tool_input: str = "") -> None:
        self._record({"node": node, "kind": "tool_call", "tool": tool, "input": tool_input})
        await self.send({
            "type": "tool_call",
            "node": node,
            "tool": tool,
            "input": (tool_input or "")[:400],
        })

    async def tool_result(self, node: str, tool: str, summary: str = "", ok: bool = True) -> None:
        self._record({"node": node, "kind": "tool_result", "tool": tool, "text": summary, "ok": ok})
        await self.send({
            "type": "tool_result",
            "node": node,
            "tool": tool,
            "summary": (summary or "")[:400],
            "ok": ok,
        })

    async def reflection(self, node: str, text: str, action: str = "") -> None:
        self._record({"node": node, "kind": "reflection", "text": text})
        await self.send({"type": "reflection", "node": node, "text": text, "action": action})

    async def token_usage(self) -> None:
        if self._token_getter is None:
            return
        try:
            usage = self._token_getter()
        except Exception:
            return
        await self.send({
            "type": "token_usage",
            "input_tokens": usage.get("input", 0),
            "output_tokens": usage.get("output", 0),
            "total_tokens": usage.get("total", 0),
        })

    async def error(self, message: str) -> None:
        await self.send({"type": "error", "message": message})

    async def gate_pending(self, gate: Dict[str, Any]) -> None:
        """The run is waiting for the user to approve or decline."""
        await self.send({"type": "gate_pending", "gate": gate})

    async def gate_decided(self, gate: Dict[str, Any]) -> None:
        """The user's decision has been recorded."""
        await self.send({"type": "gate_decided", "gate": gate})

    async def cancelled(self) -> None:
        await self.send({"type": "cancelled"})

    def _record(self, entry: Dict[str, Any]) -> None:
        if len(self._trace) < 500:
            self._trace.append(entry)
