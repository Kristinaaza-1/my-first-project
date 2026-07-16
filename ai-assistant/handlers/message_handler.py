"""
Обработка входящих сообщений от клиентов — общая логика для Telegram и WhatsApp.

Мастер (эскалации, подтверждение записи) всегда получает уведомления в свой
Telegram, независимо от того, из какого канала пишет клиент.
"""
import asyncio
from typing import Awaitable, Callable

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from calendar_service import create_event, get_free_slots
from claude_classifier import classify_message
from config import MASTER_TELEGRAM_CHAT_ID
from sheets_store import get_or_create_client, log_booking, log_conversation

SendToClient = Callable[[str], Awaitable[None]]

# chat_id мастера в Telegram -> используется, чтобы отличать его сообщения от клиентских
_bot: Bot | None = None


def set_bot(bot: Bot) -> None:
    """Вызывается один раз из bot.py после создания Application — даёт доступ
    к Telegram Bot для отправки уведомлений мастеру из любого канала (включая WhatsApp)."""
    global _bot
    _bot = bot


async def notify_master(text: str, keyboard: InlineKeyboardMarkup | None = None) -> None:
    await _bot.send_message(chat_id=MASTER_TELEGRAM_CHAT_ID, text=text, reply_markup=keyboard)


# Состояние в памяти процесса, ключ - "channel:client_id" (например "telegram:123" или "whatsapp:+79991234567")
_pending_slots: dict[str, dict] = {}

# booking_row -> (channel, client_key), чтобы booking_callback знал, куда и как ответить клиенту
booking_row_to_client: dict[int, tuple[str, str]] = {}


async def process_client_message(
    channel: str,
    client_key: str,
    client_name: str,
    message_text: str,
    send_to_client: SendToClient,
) -> None:
    state_key = f"{channel}:{client_key}"

    client_row = await asyncio.to_thread(
        get_or_create_client, name=client_name or "Без имени", channel=channel, contact=client_key
    )

    if state_key in _pending_slots:
        await _handle_slot_choice(state_key, client_row, message_text, send_to_client)
        return

    result = await asyncio.to_thread(classify_message, message_text)
    await asyncio.to_thread(log_conversation, message_text, status=result.action, client_row=client_row)

    if result.action == "escalate":
        await send_to_client("Спасибо за сообщение! Мастер ответит вам лично в ближайшее время.")
        await notify_master(f"⚠️ Требуется ваш личный ответ.\nОт клиента ({client_name}):\n\n{message_text}")

    elif result.action == "reply":
        await send_to_client(result.reply_text or "Спасибо за вопрос!")

    elif result.action == "propose_booking":
        slots = await asyncio.to_thread(get_free_slots, duration_minutes=60, max_slots=3)
        if not slots:
            await send_to_client(
                "Сейчас не вижу свободных слотов на ближайшие дни. "
                "Передам мастеру, чтобы предложила время лично."
            )
            await notify_master(
                f"Клиент {client_name} хочет записаться, свободных слотов не найдено — нужен ваш личный ответ."
            )
            return

        service_note = result.service_note or "не указано"
        _pending_slots[state_key] = {"slots": slots, "service": service_note, "client_row": client_row}
        options_text = "\n".join(
            f"{i + 1}. {slot.strftime('%d.%m %H:%M')}" for i, slot in enumerate(slots)
        )
        await send_to_client(
            f"Вот ближайшее свободное время на «{service_note}»:\n{options_text}\n\n"
            "Напишите номер варианта, который вам подходит."
        )


async def _handle_slot_choice(
    state_key: str, client_row: int, message_text: str, send_to_client: SendToClient
) -> None:
    pending = _pending_slots.pop(state_key)
    slots = pending["slots"]
    service_note = pending["service"]
    choice_index = None
    for token in message_text.split():
        if token.isdigit() and 1 <= int(token) <= len(slots):
            choice_index = int(token) - 1
            break

    if choice_index is None:
        _pending_slots[state_key] = pending  # вернуть состояние, если не поняли выбор
        options_text = "\n".join(
            f"{i + 1}. {slot.strftime('%d.%m %H:%M')}" for i, slot in enumerate(slots)
        )
        await send_to_client(f"Не поняла выбор — напишите просто номер варианта:\n{options_text}")
        return

    chosen_slot = slots[choice_index]
    channel, client_key = state_key.split(":", 1)
    booking_row = await asyncio.to_thread(
        log_booking, client_row, chosen_slot.isoformat(), status="pending", service=service_note
    )
    booking_row_to_client[booking_row] = (channel, client_key)

    await send_to_client(
        f"Записала вас на «{service_note}», {chosen_slot.strftime('%d.%m %H:%M')} — жду подтверждения от мастера."
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm:{booking_row}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"decline:{booking_row}"),
            ]
        ]
    )
    await notify_master(
        f"Новая запись ({channel}): {client_key} на «{service_note}», "
        f"{chosen_slot.strftime('%d.%m %H:%M')}. Подтвердить?",
        keyboard=keyboard,
    )


async def handle_client_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик для Telegram (регистрируется в bot.py как MessageHandler)."""
    chat_id = update.effective_chat.id

    if chat_id == MASTER_TELEGRAM_CHAT_ID:
        return

    client = update.effective_chat
    message_text = update.message.text

    async def send_to_client(text: str) -> None:
        await update.message.reply_text(text)

    await process_client_message(
        channel="telegram",
        client_key=str(chat_id),
        client_name=client.full_name or "Без имени",
        message_text=message_text,
        send_to_client=send_to_client,
    )
