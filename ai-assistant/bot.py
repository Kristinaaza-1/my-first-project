"""Точка входа: запуск Telegram-бота (long polling) + WhatsApp webhook-сервера (если настроен)."""
import asyncio
import logging
import sys
import traceback

# На Windows консоль иногда не понимает кириллицу в логах — принудительно используем UTF-8, чтобы бот не падал на logging.info с русским текстом.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ВАЖНО: настраиваем логирование ДО импорта telegram/anthropic/google-библиотек —
# некоторые из них конфигурируют root-логгер при импорте, из-за чего наш
# basicConfig() без force=True становится no-op и INFO-сообщения тихо пропадают.
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    force=True,
)

from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from config import PORT, TELEGRAM_BOT_TOKEN, WHATSAPP_INTEGRATION_ENABLED
from handlers.booking_callback import handle_booking_decision
from handlers.message_handler import handle_client_message, set_bot


async def run_whatsapp_server() -> None:
    from aiohttp import web

    from handlers.whatsapp_webhook import create_whatsapp_app

    app = create_whatsapp_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info("WhatsApp webhook слушает на порту %s", PORT)


async def main() -> None:
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .connect_timeout(20)
        .read_timeout(20)
        .write_timeout(20)
        .build()
    )

    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_client_message))
    application.add_handler(CallbackQueryHandler(handle_booking_decision))

    set_bot(application.bot)

    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logging.info("Telegram-бот запущен, ждёт сообщения...")

    if WHATSAPP_INTEGRATION_ENABLED:
        await run_whatsapp_server()
    else:
        logging.info("WhatsApp не настроен — работаю только с Telegram.")

    try:
        await asyncio.Event().wait()  # держим процесс живым бесконечно
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        raise
