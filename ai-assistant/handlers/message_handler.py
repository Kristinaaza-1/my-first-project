"""Обработка входящих сообщений от клиентов в Telegram."""
import asyncio

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from calendar_service import create_event, get_free_slots
from claude_classifier import classify_message
from config import MASTER_TELEGRAM_CHAT_ID
from sheets_store import get_or_create_client, log_booking, log_conversation

# Простое состояние в памяти процесса: chat_id клиента -> {"slots": [...], "service": "..."}
# (для пилота с одним мастером этого достаточно)
_pending_slots: dict[int, dict] = {}

# booking_row -> chat_id клиента, чтобы booking_callback знал, кому ответить после решения мастера
booking_row_to_client_chat: dict[int, int] = {}


async def handle_client_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    if chat_id == MASTER_TELEGRAM_CHAT_ID:
        # Сообщения из личного чата мастера этот обработчик не касаются
        return

    message_text = update.message.text
    client = update.effective_chat
    client_row = await asyncio.to_thread(
        get_or_create_client,
        name=client.full_name or "Без имени",
        channel="telegram",
        contact=str(chat_id),
    )

    # Если клиент отвечает на предложенные слоты записи ("1", "первый", "второй" и т.п.)
    if chat_id in _pending_slots:
        await _handle_slot_choice(update, context, chat_id, client_row, message_text)
        return

    # Синхронные вызовы (Claude API, Google Sheets/Calendar) выполняем в отдельном
    # потоке через asyncio.to_thread — иначе они блокируют event loop бота и
    # вызывают таймауты при отправке сообщений в Telegram.
    result = await asyncio.to_thread(classify_message, message_text)
    await asyncio.to_thread(log_conversation, message_text, status=result.action, client_row=client_row)

    if result.action == "escalate":
        await update.message.reply_text(
            "Спасибо за сообщение! Мастер ответит вам лично в ближайшее время."
        )
        await context.bot.send_message(
            chat_id=MASTER_TELEGRAM_CHAT_ID,
            text=f"⚠️ Требуется ваш личный ответ.\nОт клиента ({client.full_name}):\n\n{message_text}",
        )

    elif result.action == "reply":
        await update.message.reply_text(result.reply_text or "Спасибо за вопрос!")

    elif result.action == "propose_booking":
        slots = await asyncio.to_thread(get_free_slots, duration_minutes=60, max_slots=3)
        if not slots:
            await update.message.reply_text(
                "Сейчас не вижу свободных слотов на ближайшие дни. "
                "Передам мастеру, чтобы предложила время лично."
            )
            await context.bot.send_message(
                chat_id=MASTER_TELEGRAM_CHAT_ID,
                text=f"Клиент {client.full_name} хочет записаться, свободных слотов не найдено — нужен ваш личный ответ.",
            )
            return

        service_note = result.service_note or "не указано"
        _pending_slots[chat_id] = {"slots": slots, "service": service_note}
        options_text = "\n".join(
            f"{i + 1}. {slot.strftime('%d.%m %H:%M')}" for i, slot in enumerate(slots)
        )
        await update.message.reply_text(
            f"Вот ближайшее свободное время на «{service_note}»:\n{options_text}\n\n"
            "Напишите номер варианта, который вам подходит."
        )


async def _handle_slot_choice(update, context, chat_id: int, client_row: int, message_text: str) -> None:
    pending = _pending_slots.pop(chat_id)
    slots = pending["slots"]
    service_note = pending["service"]
    choice_index = None
    for token in message_text.split():
        if token.isdigit() and 1 <= int(token) <= len(slots):
            choice_index = int(token) - 1
            break

    if choice_index is None:
        _pending_slots[chat_id] = pending  # вернуть состояние, если не поняли выбор
        options_text = "\n".join(
            f"{i + 1}. {slot.strftime('%d.%m %H:%M')}" for i, slot in enumerate(slots)
        )
        await update.message.reply_text(
            f"Не поняла выбор — напишите просто номер варианта:\n{options_text}"
        )
        return

    chosen_slot = slots[choice_index]
    client = update.effective_chat
    booking_row = await asyncio.to_thread(
        log_booking, client_row, chosen_slot.isoformat(), status="pending", service=service_note
    )
    booking_row_to_client_chat[booking_row] = chat_id

    await update.message.reply_text(
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
    await context.bot.send_message(
        chat_id=MASTER_TELEGRAM_CHAT_ID,
        text=(
            f"Новая запись: {client.full_name} на «{service_note}», "
            f"{chosen_slot.strftime('%d.%m %H:%M')}. Подтвердить?"
        ),
        reply_markup=keyboard,
    )
