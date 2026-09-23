"""
backend/core/ws.py — thread-safe WebSocket wrapper.

Multiple asyncio tasks can own the same connection (e.g. a cancelled workflow
and a freshly started one). Without a send lock, concurrent send_json calls can
interleave and corrupt the JSON frames on the wire. SafeWebSocket wraps a
FastAPI WebSocket and serializes every send.
"""
import asyncio
from typing import Any

from fastapi import WebSocket


class SafeWebSocket:
    """Duck-typed WebSocket whose send_json calls are serialized by a lock."""

    def __init__(self, websocket: WebSocket) -> None:
        self._ws = websocket
        self._send_lock = asyncio.Lock()

    async def accept(self) -> None:
        await self._ws.accept()

    async def receive_json(self) -> Any:
        return await self._ws.receive_json()

    async def send_json(self, content: Any) -> None:
        async with self._send_lock:
            await self._ws.send_json(content)