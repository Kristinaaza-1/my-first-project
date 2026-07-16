"""Загрузка конфигурации из переменных окружения."""
import os

from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]

# Chat ID мастера в Telegram — куда бот шлёт эскалации и запросы на подтверждение записи
MASTER_TELEGRAM_CHAT_ID = int(os.environ["MASTER_TELEGRAM_CHAT_ID"])

# --- Всё ниже НЕОБЯЗАТЕЛЬНО для первого запуска ---
# Google Sheets/Calendar подключаются позже отдельным шагом. Пока эти переменные
# не заполнены, бот работает в "минимальном режиме": отвечает на рутинные вопросы,
# эскалирует чувствительные темы, а вместо записи в календарь просит клиента
# уточнить время у мастера лично. Ничего не падает и не требует Google Cloud.

# Путь к JSON-файлу сервис-аккаунта Google ИЛИ его содержимое как строка (для деплоя без файловой системы, например Railway)
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
GOOGLE_SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json")

GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID")

GOOGLE_INTEGRATION_ENABLED = bool(GOOGLE_SHEET_ID and GOOGLE_CALENDAR_ID and (GOOGLE_SERVICE_ACCOUNT_JSON or os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE)))

# WhatsApp Cloud API — подключается отдельным шагом (Meta App Review). Пока не
# заполнено, WhatsApp-канал просто не запускается, Telegram работает как обычно.
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN")

WHATSAPP_INTEGRATION_ENABLED = bool(
    WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_VERIFY_TOKEN
)

# Порт для веб-сервера (нужен только для WhatsApp webhook) — Railway передаёт его сам
PORT = int(os.environ.get("PORT", "8080"))
