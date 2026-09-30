"""
backend/api/whatsapp.py — WhatsApp Cloud API webhook (Meta) — OPTIONAL scaffold.

Endpoints:
- GET  /api/whatsapp/webhook  Meta verification handshake (?hub.mode, hub.verify_token, hub.challenge)
- POST /api/whatsapp/webhook  incoming messages → chat_agent brain → Graph API reply

The brain is the same scope-limited business chatbot as the web ChatPanel
(loans, schemes, documents, building the business; Hindi/Hinglish supported).
Each sender gets an isolated memory namespace (wa-<sender>) so chat memory
never leaks across users.

Setup (Meta Developers → WhatsApp → API Setup):
  WHATSAPP_VERIFY_TOKEN    any secret string you invent (Meta echoes it back once)
  WHATSAPP_TOKEN           permanent system-user token
  WHATSAPP_PHONE_NUMBER_ID the sender's Phone Number ID
Then set the webhook URL to https://<your-backend>/api/whatsapp/webhook.

Never hard-fails Meta: verification mismatches return 403 (per Meta spec);
message handling always returns 200 so Meta does not retry-storm.
"""
import logging

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse

from backend.core.config import (
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
    WHATSAPP_VERIFY_TOKEN,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

_GRAPH_VERSION = "v20.0"


@router.get("/webhook")
async def whatsapp_verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_verify_token: str = Query("", alias="hub.verify_token"),
    hub_challenge: str = Query("", alias="hub.challenge"),
):
    """Meta verification handshake — echoes hub.challenge on token match."""
    if not WHATSAPP_VERIFY_TOKEN:
        logger.warning("[WhatsApp] verification attempted but WHATSAPP_VERIFY_TOKEN unset")
        return PlainTextResponse("WhatsApp webhook not configured.", status_code=503)
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("[WhatsApp] webhook verified.")
        return PlainTextResponse(hub_challenge or "")
    logger.warning("[WhatsApp] verification failed (token mismatch).")
    return PlainTextResponse("Verification failed.", status_code=403)


def _extract_texts(payload: dict) -> list[tuple[str, str]]:
    """Pull (sender, text) pairs out of a Meta Cloud API payload. Never raises."""
    out: list[tuple[str, str]] = []
    try:
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                value = change.get("value", {}) or {}
                for msg in value.get("messages", []) or []:
                    if msg.get("type") != "text":
                        continue
                    body = ((msg.get("text") or {}).get("body") or "").strip()
                    sender = (msg.get("from") or "").strip()
                    if body and sender:
                        out.append((sender, body))
    except Exception as e:
        logger.warning(f"[WhatsApp] payload parse failed: {e}")
    return out


async def _send_reply(to: str, text: str) -> bool:
    """Deliver a text reply via the Graph API. Returns success. Never raises."""
    if not (WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID):
        logger.warning("[WhatsApp] reply skipped — WHATSAPP_TOKEN/PHONE_NUMBER_ID unset.")
        return False
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"https://graph.facebook.com/{_GRAPH_VERSION}/"
                f"{WHATSAPP_PHONE_NUMBER_ID}/messages",
                headers={
                    "Authorization": f"Bearer {WHATSAPP_TOKEN}",
                    "Content-Type": "application/json",
                },
                json={
                    "messaging_product": "whatsapp",
                    "to": to,
                    "type": "text",
                    "text": {"body": text[:4000], "preview_url": False},
                },
            )
        if resp.status_code in (200, 201):
            return True
        logger.warning(f"[WhatsApp] Graph API {resp.status_code}: {resp.text[:200]}")
        return False
    except Exception as e:
        logger.warning(f"[WhatsApp] send failed: {e}")
        return False


@router.post("/webhook")
async def whatsapp_incoming(request: Request):
    """Handle incoming messages. Always 200 (Meta retries on anything else)."""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ignored (not JSON)"}

    pairs = _extract_texts(payload if isinstance(payload, dict) else {})
    if not pairs:
        return {"status": "ignored (no text messages)"}

    from backend.agents.chat import chat_agent

    for sender, body in pairs:
        session_id = f"wa-{sender}"
        try:
            reply = await chat_agent(body, agent_hint="chat")
        except Exception as e:
            logger.error(f"[WhatsApp] brain failed for {session_id}: {e}")
            reply = (
                "Namaste! Main GrameenAI hoon — business aur loan mein madad karta hoon. "
                "Abhi thodi dikkat hai, thodi der baad fir se likhiye."
            )
        await _send_reply(sender, reply)

    return {"status": "processed", "count": len(pairs)}
