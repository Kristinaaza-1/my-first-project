"""Webhook-эндпоинты для WhatsApp Cloud API (aiohttp)."""
import asyncio
import logging

from aiohttp import web

from config import WHATSAPP_VERIFY_TOKEN
from handlers.message_handler import process_client_message
from whatsapp_client import send_text_message


async def verify_webhook(request: web.Request) -> web.Response:
    """Meta присылает GET-запрос при подключении вебхука — нужно подтвердить verify_token."""
    mode = request.query.get("hub.mode")
    token = request.query.get("hub.verify_token")
    challenge = request.query.get("hub.challenge", "")

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return web.Response(text=challenge)
    return web.Response(status=403)


async def receive_message(request: web.Request) -> web.Response:
    """Meta присылает POST-запрос с входящими сообщениями."""
    payload = await request.json()
    logging.info("WhatsApp incoming payload: %s", payload)

    try:
        entries = payload.get("entry", [])
        for entry in entries:
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                if not messages:
                    continue  # это может быть просто статус доставки, не сообщение

                contacts = value.get("contacts", [{}])
                contact_name = contacts[0].get("profile", {}).get("name", "Без имени") if contacts else "Без имени"

                for message in messages:
                    if message.get("type") != "text":
                        continue
                    from_number = message["from"]
                    text_body = message["text"]["body"]

                    async def send_to_client(text: str, _to=from_number) -> None:
                        await asyncio.to_thread(send_text_message, _to, text)

                    await process_client_message(
                        channel="whatsapp",
                        client_key=from_number,
                        client_name=contact_name,
                        message_text=text_body,
                        send_to_client=send_to_client,
                    )
    except Exception:
        logging.exception("Ошибка обработки входящего WhatsApp-сообщения")

    return web.Response(text="OK")


def create_whatsapp_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/webhook/whatsapp", verify_webhook)
    app.router.add_post("/webhook/whatsapp", receive_message)
    return app
