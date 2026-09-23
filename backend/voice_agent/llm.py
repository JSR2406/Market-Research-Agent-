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

from livekit.agents import llm as agents_llm

from backend.core.heuristics import schemes_json
from backend.core.llm_client import call_llm

logger = logging.getLogger(__name__)

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


def _as_chat_messages(livekit_messages):
    """Convert LiveKit LLMRequest messages to OpenAI-style role/content dicts."""
    out = []
    for m in livekit_messages:
        role = getattr(m, "role", "user")
        content = getattr(m, "content", "")
        out.append({"role": role, "content": content})
    return out


class AdvisoryLLM(agents_llm.LLM):
    """Custom LiveKit LLM that streams responses from the project's call_llm."""

    def __init__(self) -> None:
        super().__init__()
        self.label = "GrameenAI-AdvisoryLLM"

    def chat(self, req: agents_llm.LLMRequest) -> agents_llm.LLMStream:
        async def _gen():
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
            history.extend(_as_chat_messages(req.messages))
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
            # LiveKit taps chunks via stream.text_stream
            for i in range(0, len(text), 24):
                await asyncio.sleep(0.01)
                chunk = text[i : i + 24]
                yield agents_llm.ChatChunk(
                    choices=[
                        agents_llm.ChatChoice(
                            delta=agents_llm.ChatDelta(content=chunk),
                            index=0,
                        )
                    ]
                )

        return agents_llm.LLMStream(request=req, _generator_fn=_gen)