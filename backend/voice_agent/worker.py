"""
worker.py — LiveKit realtime voice advisory agent (separate process).

Audio pipeline:
    user mic (browser) -> LiveKit room -> Silero local STT
    -> AdvisoryLLM (multi-provider LLM + heuristic fallback)
    -> ElevenLabs TTS -> LiveKit room -> browser speakers

Run:
    pip install -r backend/requirements-voice.txt
    python -m backend.voice_agent.worker

Requirements (backend/.env):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, ELEVENLABS_API_KEY

Get free LiveKit creds at https://cloud.livekit.io (or self-host lk-server).
The browser joins the same LIVEKIT_ADVISOR_ROOM using the token minted by
POST /api/voice/livekit-token.
"""
from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("backend.voice_agent.worker")


async def run_voice_agent() -> None:
    # Optional dependencies are imported lazily so this package never breaks
    # the main FastAPI app when the voice stack is not installed.
    try:
        from livekit import api, rtc
        from livekit.agents.voice import RoomInputOptions, VoicePipelineAgent
        from livekit.plugins import elevenlabs, silero
    except ImportError:
        raise SystemExit(
            "LiveKit dependencies are missing.\n"
            "Install them with:  pip install -r backend/requirements-voice.txt"
        )

    from backend.core.config import (
        LIVEKIT_ADVISOR_ROOM,
        LIVEKIT_API_KEY,
        LIVEKIT_API_SECRET,
        LIVEKIT_URL,
    )
    from backend.voice_agent.llm import AdvisoryLLM

    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise SystemExit(
            "LiveKit is not configured. Add LIVEKIT_URL, LIVEKIT_API_KEY and "
            "LIVEKIT_API_SECRET to backend/.env (see backend/.env.example)."
        )

    import os

    if not os.getenv("ELEVENLABS_API_KEY"):
        logger.warning(
            "ELEVENLABS_API_KEY is not set in backend/.env — ElevenLabs TTS will "
            "fail loudly when the agent tries to speak."
        )

    agent_token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity("advisor-agent")
        .with_name("GrameenAI Advisor")
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=LIVEKIT_ADVISOR_ROOM,
                can_publish=True,
                can_subscribe=True,
            )
        )
    )

    logger.info("Connecting to LiveKit room '%s' at %s", LIVEKIT_ADVISOR_ROOM, LIVEKIT_URL)
    room = rtc.Room()
    await room.connect(LIVEKIT_URL, agent_token.to_jwt())

    agent = VoicePipelineAgent(
        stt=silero.STTR(),
        llm=AdvisoryLLM(),
        tts=elevenlabs.TTS(),
        allow_interruptions=True,
        min_endpointing_delay=0.5,
    )
    await agent.start(room, room_input_options=RoomInputOptions(audio=True, video=False))

    logger.info("Voice agent running. Speak from the browser panel. Ctrl+C to stop.")
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await agent.stop()
        await room.disconnect()
        logger.info("Voice agent stopped.")


def main() -> None:
    try:
        asyncio.run(run_voice_agent())
    except KeyboardInterrupt:
        print("\nVoice agent stopped by user.")
        sys.exit(0)
    except SystemExit as e:
        print(f"{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()