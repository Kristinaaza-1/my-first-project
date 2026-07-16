"""Обработка нажатий мастера на кнопки Подтвердить/Отклонить запись."""
import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import ContextTypes

from calendar_service import create_event
from handlers.message_handler import booking_row_to_client
from sheets_store import get_booking, update_booking_status
from whatsapp_client import send_text_message as send_whatsapp_message

DEFAULT_DURATION_MINUTES = 60


async def _send_to_client(channel: str, client_key: str, text: str, context: ContextTypes.DEFAULT_TYPE) -> None:
    if channel == "telegram":
        await context.bot.send_message(chat_id=int(client_key), text=text)
    elif channel == "whatsapp":
        await asyncio.to_thread(send_whatsapp_message, client_key, text)


async def handle_booking_decision(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    action, booking_row_str = query.data.split(":")
    booking_row = int(booking_row_str)
    client_channel_key = booking_row_to_client.get(booking_row)

    booking = await asyncio.to_thread(get_booking, booking_row)
    proposed_time = datetime.fromisoformat(booking["proposed_time"])
    service_note = booking.get("service") or "не указано"

    if action == "confirm":
        await asyncio.to_thread(
            create_event,
            start_time=proposed_time,
            duration_minutes=DEFAULT_DURATION_MINUTES,
            summary=f"Запись: {service_note}",
        )
        await asyncio.to_thread(update_booking_status, booking_row, "confirmed_by_master")
        await query.edit_message_text(
            f"✅ Подтверждено: «{service_note}», {proposed_time.strftime('%d.%m %H:%M')}"
        )

        if client_channel_key:
            channel, client_key = client_channel_key
            await _send_to_client(
                channel, client_key, f"Вы записаны на {proposed_time.strftime('%d.%m %H:%M')}! Ждём вас 🙂", context
            )

    elif action == "decline":
        await asyncio.to_thread(update_booking_status, booking_row, "declined")
        await query.edit_message_text(
            f"❌ Отклонено: «{service_note}», {proposed_time.strftime('%d.%m %H:%M')}"
        )

        if client_channel_key:
            channel, client_key = client_channel_key
            await _send_to_client(
                channel,
                client_key,
                "К сожалению, это время не подходит мастеру. Напишите, пожалуйста, ещё раз, чтобы подобрать другое время.",
                context,
            )
