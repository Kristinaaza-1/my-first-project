"""
Хранилище данных в Google Sheets (таблица с тремя листами: Clients, Conversations, Bookings).
Доступ через сервис-аккаунт Google — таблица должна быть расшарена на его email с правом редактирования.

Если Google-интеграция ещё не настроена (GOOGLE_INTEGRATION_ENABLED = False),
все функции работают как no-op с понятным выводом в консоль — бот не падает
и не требует Google Cloud для первого теста.
"""
import json
import logging
from datetime import datetime, timezone

from config import (
    GOOGLE_INTEGRATION_ENABLED,
    GOOGLE_SERVICE_ACCOUNT_FILE,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_SHEET_ID,
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/calendar",
]

_gc = None
_sheet = None
_clients_ws = None
_conversations_ws = None
_bookings_ws = None


def get_credentials():
    from google.oauth2.service_account import Credentials

    if GOOGLE_SERVICE_ACCOUNT_JSON:
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    return Credentials.from_service_account_file(GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES)


if GOOGLE_INTEGRATION_ENABLED:
    import gspread

    _gc = gspread.authorize(get_credentials())
    _sheet = _gc.open_by_key(GOOGLE_SHEET_ID)
    _clients_ws = _sheet.worksheet("Clients")
    _conversations_ws = _sheet.worksheet("Conversations")
    _bookings_ws = _sheet.worksheet("Bookings")
else:
    logging.warning(
        "Google Sheets не настроен — работаю в минимальном режиме, данные не сохраняются в таблицу."
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_or_create_client(name: str, channel: str, contact: str) -> int:
    """Возвращает номер строки клиента в листе Clients, создаёт запись, если её ещё нет.
    В минимальном режиме возвращает 0 (заглушка, ни на что не влияет)."""
    if not GOOGLE_INTEGRATION_ENABLED:
        return 0

    records = _clients_ws.get_all_records()
    for idx, row in enumerate(records, start=2):  # строка 1 — заголовки
        if str(row.get("Contact")) == str(contact):
            return idx
    _clients_ws.append_row([name, channel, contact, ""])
    return len(records) + 2


def log_conversation(message: str, status: str, client_row: int) -> None:
    if not GOOGLE_INTEGRATION_ENABLED:
        logging.info("[Sheets отключён] Conversation: %s | %s", status, message)
        return
    _conversations_ws.append_row([message, status, client_row, _now()])


def log_booking(
    client_row: int, proposed_time_iso: str, status: str = "pending", service: str = ""
) -> int:
    if not GOOGLE_INTEGRATION_ENABLED:
        logging.info("[Sheets отключён] Booking: %s | %s | %s", proposed_time_iso, status, service)
        return 0
    _bookings_ws.append_row([client_row, proposed_time_iso, status, service])
    return len(_bookings_ws.get_all_values())  # номер строки новой записи


def update_booking_status(booking_row: int, status: str) -> None:
    if not GOOGLE_INTEGRATION_ENABLED:
        return
    _bookings_ws.update_cell(booking_row, 3, status)


def get_booking(booking_row: int) -> dict:
    if not GOOGLE_INTEGRATION_ENABLED:
        return {"client_row": None, "proposed_time": None, "status": None, "service": None}
    values = _bookings_ws.row_values(booking_row)
    return {
        "client_row": values[0] if len(values) > 0 else None,
        "proposed_time": values[1] if len(values) > 1 else None,
        "status": values[2] if len(values) > 2 else None,
        "service": values[3] if len(values) > 3 else None,
    }
