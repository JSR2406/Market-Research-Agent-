import hashlib
import hmac
import json
import logging
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse

from backend.agents.chat import chat_agent
from backend.core.config import (
    WHATSAPP_APP_SECRET,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_TOKEN,
    WHATSAPP_VERIFY_TOKEN,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


def _is_configured() -> bool:
    return bool(WHATSAPP_TOKEN and WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_VERIFY_TOKEN)


def _verify_signature(payload: bytes, supplied: str | None) -> bool:
    if not WHATSAPP_APP_SECRET:
        return True
    if not supplied:
        return False
    expected = "sha256=" + hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied.strip())


@router.get("/webhook")
async def whatsapp_verify(request: Request):
    """Meta webhook verification challenge."""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN and challenge:
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Invalid verification request.")


async def _send_whatsapp_text(to_phone: str, text: str) -> None:
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise RuntimeError("WhatsApp is not configured.")

    url = f"https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text[:2000]},
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()


def _extract_message_payload(data: Dict[str, Any]) -> Optional[tuple[str, str]]:
    try:
        entry = data.get("entry") or []
        for item in entry:
            changes = item.get("changes") or []
            for change in changes:
                value = change.get("value") or {}
                messages = value.get("messages") or []
                for message in messages:
                    if message.get("type") != "text":
                        continue
                    from_phone = str(message.get("from") or "").strip()
                    body = str((message.get("text") or {}).get("body") or "").strip()
                    if from_phone and body:
                        return from_phone, body
    except Exception:
        return None
    return None


@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """Receive Meta webhook events and reply using the same chat brain."""
    raw = await request.body()

    if not _is_configured():
        logger.warning("[whatsapp] webhook hit but WhatsApp is not configured")
        raise HTTPException(status_code=503, detail="WhatsApp not configured.")

    supplied_sig = request.headers.get("x-hub-signature-256")
    if not _verify_signature(raw, supplied_sig):
        logger.warning("[whatsapp] rejected unsigned webhook request")
        raise HTTPException(status_code=403, detail="Signature verification failed.")

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        logger.warning("[whatsapp] invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid payload.")

    result = _extract_message_payload(payload)
    if not result:
        return {"status": "ok"}

    from_phone, body = result
    session_id = f"wa-{from_phone.replace('+', '').replace(' ', '')}"

    try:
        reply = await chat_agent(
            body,
            topic="WhatsApp chat",
            lang="auto",
            profile="",
            intake={},
            session_id=session_id,
        )
    except Exception as exc:
        logger.exception("[whatsapp] chat_agent failed: %s", exc)
        reply = "I hit a temporary issue. Please try again in a moment."

    try:
        await _send_whatsapp_text(from_phone, reply)
    except Exception as exc:
        logger.exception("[whatsapp] reply send failed: %s", exc)

    return {"status": "ok"}
