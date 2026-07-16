"""Точка входа: запуск Telegram-бота (long polling)."""
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

from config import TELEGRAM_BOT_TOKEN
from handlers.booking_callback import handle_booking_decision
from handlers.message_handler import handle_client_message


def main() -> None:
    # Python 3.14 больше не создаёт event loop автоматически в главном потоке —
    # python-telegram-bot этого ожидает, так что создаём его сами явно.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    # Увеличенные таймауты — по умолчанию (5с) иногда не хватает на медленном/нестабильном соединении.
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

    logging.info("Бот запущен, ждёт сообщения...")
    application.run_polling()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        raise
