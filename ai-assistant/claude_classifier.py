"""
Классификация входящих сообщений клиента через Claude API:
- escalate       — чувствительная/сложная тема (здоровье, жалобы, нестандартный случай) -> сразу к мастеру, без обработки содержания
- reply          — рутинный вопрос (цена/адрес/подготовка) -> готовый текст ответа клиенту
- propose_booking — клиент хочет записаться -> нужно предложить свободное время
"""
import json
from dataclasses import dataclass
from typing import Literal

import anthropic

from config import ANTHROPIC_API_KEY
from knowledge_base import build_knowledge_base_text

# Sonnet — надёжнее для решения "эскалировать или нет", это самое важное решение в системе.
# Можно позже перейти на более дешёвую модель (claude-haiku-4-5-20251001), когда логика проверена на практике.
MODEL = "claude-sonnet-5"

Action = Literal["escalate", "reply", "propose_booking"]


@dataclass
class ClassificationResult:
    action: Action
    reply_text: str | None = None
    service_note: str | None = None  # какая услуга упомянута клиентом (для propose_booking)


SYSTEM_PROMPT = """Ты — ассистент-администратор мастера в бьюти-индустрии (косметолог).
Твоя задача — прочитать сообщение клиента и решить, что с ним делать.

У тебя есть база знаний мастера (прайс, адрес, инструкции подготовки, условия отмены).

Правила (СТРОГО соблюдать):
1. Если сообщение касается здоровья, аллергий, противопоказаний, беременности,
   жалоб, конфликтов, или ЛЮБОЙ неоднозначной/нестандартной ситуации — верни
   action "escalate". НЕ пытайся отвечать на такие темы сам, даже частично.
   При любом сомнении — выбирай escalate, а не reply.
2. Если вопрос рутинный и однозначно покрыт базой знаний (цена, адрес, часы
   работы, подготовка к процедуре, условия отмены) — верни action "reply" и
   готовый текст ответа клиенту на основе базы знаний, дружелюбным тоном.
3. Если клиент явно хочет записаться на процедуру (спрашивает про свободное
   время / просит записать) — верни action "propose_booking" и в поле
   "service_note" укажи, на какую именно услугу из прайса похоже хочет
   записаться клиент (по названию услуги из базы знаний, если понятно из
   сообщения) — например "Глубокое обёртывание". Если из сообщения не ясно,
   какая именно услуга нужна — укажи "не указано".
4. Если непонятно, что хочет клиент — выбирай "escalate", не гадай.

Отвечай СТРОГО в формате JSON, без markdown-разметки, без пояснений:
{"action": "escalate" | "reply" | "propose_booking", "reply_text": "текст ответа или null", "service_note": "название услуги или null"}
"""


def classify_message(client_message: str) -> ClassificationResult:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_content = f"""База знаний мастера:
{build_knowledge_base_text()}

Сообщение клиента:
\"\"\"{client_message}\"\"\"
"""

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Sonnet иногда возвращает блок "размышлений" (ThinkingBlock) перед текстом —
    # ищем именно текстовый блок, а не полагаемся на индекс 0.
    raw_text = next(
        (block.text for block in response.content if block.type == "text"), ""
    ).strip()

    try:
        parsed = json.loads(raw_text)
        action = parsed.get("action")
        if action not in ("escalate", "reply", "propose_booking"):
            action = "escalate"
        return ClassificationResult(
            action=action,
            reply_text=parsed.get("reply_text"),
            service_note=parsed.get("service_note"),
        )
    except (json.JSONDecodeError, IndexError, KeyError):
        # Если модель вернула что-то нестандартное — безопасный дефолт: эскалация к человеку.
        return ClassificationResult(action="escalate", reply_text=None)
