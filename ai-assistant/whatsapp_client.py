"""Отправка сообщений через WhatsApp Cloud API."""
import logging

import httpx

from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID

GRAPH_API_URL = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"


def send_text_message(to: str, text: str) -> None:
    """Отправляет текстовое сообщение клиенту WhatsApp по номеру `to`."""
    response = httpx.post(
        GRAPH_API_URL,
        headers={"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        },
        timeout=20,
    )
    logging.info("WhatsApp send_text_message to=%s status=%s body=%s", to, response.status_code, response.text)
    response.raise_for_status()
