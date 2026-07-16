"""
Работа с Google Calendar мастера через тот же сервис-аккаунт, что и Sheets.
Календарь мастера должен быть расшарен на email сервис-аккаунта с правом
"Making changes to events".

Если Google-интеграция ещё не настроена, get_free_slots() возвращает пустой
список — message_handler.py уже понимает это как "слотов нет" и эскалирует
запись на приём мастеру лично. Бот не падает и не требует Google Cloud для
первого теста.
"""
import logging
from datetime import datetime, timedelta, timezone

from config import GOOGLE_CALENDAR_ID, GOOGLE_INTEGRATION_ENABLED
from sheets_store import get_credentials

WORKDAY_START_HOUR = 10
WORKDAY_END_HOUR = 22
SLOT_MINUTES = 60
DAYS_AHEAD_TO_SCAN = 5

_service = None

if GOOGLE_INTEGRATION_ENABLED:
    from googleapiclient.discovery import build

    _service = build("calendar", "v3", credentials=get_credentials())


def get_free_slots(duration_minutes: int = 60, max_slots: int = 3) -> list[datetime]:
    """Простой поиск свободных слотов в ближайшие дни в рамках рабочих часов.

    Не претендует на промышленную сложность — этого достаточно для пилота с одним мастером.
    """
    if not GOOGLE_INTEGRATION_ENABLED:
        logging.info("[Calendar отключён] Свободные слоты не ищем, эскалируем мастеру.")
        return []

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=DAYS_AHEAD_TO_SCAN)).isoformat()

    freebusy = _service.freebusy().query(
        body={
            "timeMin": time_min,
            "timeMax": time_max,
            "items": [{"id": GOOGLE_CALENDAR_ID}],
        }
    ).execute()

    busy_periods = freebusy["calendars"][GOOGLE_CALENDAR_ID]["busy"]
    busy_ranges = [
        (datetime.fromisoformat(b["start"]), datetime.fromisoformat(b["end"]))
        for b in busy_periods
    ]

    free_slots: list[datetime] = []
    day_cursor = now.replace(minute=0, second=0, microsecond=0)

    for _ in range(DAYS_AHEAD_TO_SCAN * (WORKDAY_END_HOUR - WORKDAY_START_HOUR)):
        if len(free_slots) >= max_slots:
            break

        candidate_start = day_cursor
        candidate_end = candidate_start + timedelta(minutes=duration_minutes)
        day_cursor += timedelta(hours=1)

        if not (WORKDAY_START_HOUR <= candidate_start.hour < WORKDAY_END_HOUR):
            continue
        if candidate_start < now:
            continue

        overlaps = any(
            candidate_start < busy_end and candidate_end > busy_start
            for busy_start, busy_end in busy_ranges
        )
        if not overlaps:
            free_slots.append(candidate_start)

    return free_slots


def create_event(start_time: datetime, duration_minutes: int, summary: str) -> str | None:
    """Создаёт событие в календаре мастера, возвращает event id (или None, если интеграция отключена)."""
    if not GOOGLE_INTEGRATION_ENABLED:
        logging.info("[Calendar отключён] Событие не создано: %s в %s", summary, start_time)
        return None

    end_time = start_time + timedelta(minutes=duration_minutes)
    event = {
        "summary": summary,
        "start": {"dateTime": start_time.isoformat()},
        "end": {"dateTime": end_time.isoformat()},
    }
    created = _service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return created["id"]
