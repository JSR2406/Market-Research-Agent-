"""
llm.py — LiveKit LLM adapter for the realtime voice advisor.

Bridges LiveKit's conversational pipeline to the project's existing multi-
provider brain (backend/core/llm_client.call_llm with per-agent models + key
rotation + bounded cache + heuristic fallback), so the voice advisor and the
text advisory pipeline share the same reliable LLM path.

Targets livekit-agents==1.8.x. Run only from the voice worker process where
`livekit-agents` is installed (backend/requirements-voice.txt).
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from livekit.agents import llm as agents_llm

from backend.core.heuristics import schemes_json
from backend.core.llm_client import call_llm

logger = logging.getLogger("backend.voice_agent.llm")

_SCHEMES_EXCERPT = schemes_json()[:1500]

SYSTEM_PROMPT = (
    "You are GrameenAI, a friendly spoken loan advisor for Indian MSME business "
    "owners, street vendors and small shopkeepers. Answer out loud, so keep every "
    "reply short, simple, and in plain, easy-to-understand language. Be warm and "
    "practical. If asked about a loan or government scheme, match it against the "
    "curated scheme list below and suggest only schemes in the list. If you do not "
    "know something, say so honestly and suggest what to ask their bank.\n\n"
    f"CURATED INDIAN MSME SCHEMES (use these, never invent others):\n{_SCHEMES_EXCERPT}"
)


def _as_chat_messages(chat_ctx: agents_llm.ChatContext) -> list[dict[str, str]]:
    """Convert a LiveKit ChatContext to OpenAI-style role/content dicts."""
    out = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in chat_ctx.items:
        role = getattr(item, "role", "user") or "user"
        content = getattr(item, "content", "")
        if isinstance(content, list):  # content blocks (text/image parts)
            content = " ".join(
                getattr(part, "text", "") or "" for part in content
            ).strip()
        if role not in ("system", "user", "assistant"):
            role = "user"
        out.append({"role": role, "content": str(content)})
    return out


class _AdvisoryStream(agents_llm.LLMStream):
    """Pushes call_llm output into the session as ChatChunks."""

    async def _run(self) -> None:
        history = _as_chat_messages(self.chat_ctx)
        try:
            text = await call_llm(history, temperature=0.6, agent_hint="voice")
        except Exception as e:
            logger.error(f"[VoiceLLM] brain failed, falling back: {e}")
            text = (
                "I am having trouble reaching my knowledge right now. "
                "Please try asking again in a moment, or check the written "
                "advisory on screen."
            )
        text = text.strip() or "I did not catch that. Could you say it again, please?"
        # LiveKit taps chunks via the stream's event channel.
        for i in range(0, len(text), 24):
            await asyncio.sleep(0.01)
            self._event_ch.send_nowait(
                agents_llm.ChatChunk(
                    id=str(uuid.uuid4()),
                    delta=agents_llm.ChoiceDelta(
                        content=text[i : i + 24], role="assistant"
                    ),
                )
            )


class AdvisoryLLM(agents_llm.LLM):
    """Custom LiveKit LLM that streams responses from the project's call_llm."""

    def __init__(self) -> None:
        super().__init__()

    def chat(
        self,
        *,
        chat_ctx: agents_llm.ChatContext,
        tools: list | None = None,
        conn_options=None,
        parallel_tool_calls=None,
        tool_choice=None,
        extra_kwargs=None,
    ) -> agents_llm.LLMStream:
        return _AdvisoryStream(
            llm=self, chat_ctx=chat_ctx, tools=tools or [], conn_options=conn_options
        )
