# LangGraph — Шаблоны кода для узлов графа

## Состояние диалога (src/ai/states.py)

```python
from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages


class TourParams(TypedDict, total=False):
    destination: str       # "Турция", "Египет" и т.д.
    dates: str              # "август", "15-22 июня" и т.д.
    budget: str             # "2000$", "до 1500$" и т.д.
    travelers: int         # количество человек
    tour_type: str          # "пляж", "экскурсии", "горы" и т.д.


class DialogState(TypedDict):
    """Полное состояние диалога с клиентом."""

    messages: Annotated[list, add_messages]
    client_id: str                      # Instagram user ID
    client_name: Optional[str]           # Имя (из Instagram или собранное)
    client_phone: Optional[str]          # Телефон (собранный)
    client_email: Optional[str]          # Email (собранный)
    request_type: Literal[
        "tour_search", "faq", "complaint",
        "talk_to_manager", "booking", "greeting", "unknown"
    ] | None
    tour_params: TourParams              # Извлечённые параметры тура
    found_tours: list[dict]              # Найденные туры (из Google Sheets)
    selected_tour: Optional[str]         # Выбранный тур (название)
    faq_answer: Optional[str]           # Ответ из FAQ
    needs_escalation: bool               # Триггер передачи менеджеру
    escalation_reason: Optional[str]     # Причина эскалации
    current_step: str                    # Текущий этап (для clarification)
    awaiting_field: Optional[str]        # Какое поле ожидается (name/phone/email)
    conversation_history: list[dict]    # История переписки для уведомления
```

## Граф диалога (src/ai/engine.py)

```python
from langgraph.graph import StateGraph, END

from src.ai.states import DialogState
from src.ai.nodes import (
    greet,
    classify,
    clarify,
    search_tours,
    present_tours,
    book,
    faq_search,
    escalate,
)


def build_graph() -> StateGraph:
    """Создаёт граф состояний диалога."""

    graph = StateGraph(DialogState)

    # Регистрация узлов
    graph.add_node("greeting", greet)
    graph.add_node("classify", classify)
    graph.add_node("clarify", clarify)
    graph.add_node("search_tours", search_tours)
    graph.add_node("present_tours", present_tours)
    graph.add_node("book", book)
    graph.add_node("faq_search", faq_search)
    graph.add_node("escalate", escalate)

    # Начальная точка
    graph.set_entry_point("greeting")

    # ТранзITIONS
    graph.add_edge("greeting", "classify")

    graph.add_conditional_edges(
        "classify",
        route_by_request_type,
        {
            "tour_search": "clarify",
            "faq": "faq_search",
            "complaint": "escalate",
            "talk_to_manager": "escalate",
            "booking": "book",
            "unknown": "classify",
        },
    )

    graph.add_edge("clarify", "search_tours")
    graph.add_edge("search_tours", "present_tours")

    graph.add_conditional_edges(
        "present_tours",
        route_after_presentation,
        {
            "book": "book",
            "escalate": "escalate",
            "end": END,
        },
    )

    graph.add_edge("faq_search", END)
    graph.add_edge("book", END)
    graph.add_edge("escalate", END)

    return graph.compile()


def route_by_request_type(state: DialogState) -> str:
    """Маршрутизация после классификации."""
    request_type = state.get("request_type", "unknown")
    return request_type


def route_after_presentation(state: DialogState) -> str:
    """Маршрутизация после выдачи результатов."""
    if state.get("needs_escalation"):
        return "escalate"
    if state.get("selected_tour"):
        return "book"
    return "end"
```

## Узел: Классификация (src/ai/classifier.py)

```python
from src.ai.states import DialogState
from src.services.llm import get_llm

CLASSIFICATION_PROMPT = """Ты — классификатор запросов для туристического агентства.

Классифицируй сообщение клиента в одну из категорий:
- tour_search: клиент ищет тур, спрашивает о направлениях, ценах, датах
- faq: клиент задаёт общий вопрос (визы, страховка, погода, документы, правила въезда)
- complaint: клиент жалуется, недоволен, просит решить проблему
- talk_to_manager: клиент прямо просит поговорить с живым человеком / менеджером / оператором
- booking: клиент хочет записаться / забронировать / оплатить
- unknown: не удалось определить

Также проверь, не содержит ли сообщение триггеров эскалации:
- Слова: "срочно", "жалоба", "недоволен", "проблема"
- Запрос индивидуального подбора
- Слишком сложный/нестандартный запрос

Ответь строго в формате JSON:
{
  "request_type": "tour_search|faq|complaint|talk_to_manager|booking|unknown",
  "needs_escalation": false,
  "escalation_reason": null
}

Сообщение клиента:
{message}
"""


async def classify(state: DialogState) -> dict:
    """Классифицирует тип запроса клиента."""

    last_message = state["messages"][-1].content if state["messages"] else ""

    llm = get_llm()
    response = await llm.ainvoke(
        CLASSIFICATION_PROMPT.format(message=last_message)
    )

    # Парсим JSON-ответ
    import json
    result = json.loads(response.content)

    return {
        "request_type": result["request_type"],
        "needs_escalation": result.get("needs_escalation", False),
        "escalation_reason": result.get("escalation_reason"),
    }
```

## Узел: Уточнение параметров (src/ai/nodes.py — clarify)

```python
EXTRACT_PROMPT = """Извлеки из сообщения клиента параметры тура. Если параметр не указан — оставь null.

Параметры:
- destination: страна или город (например: "Турция", "Анталья")
- dates: даты или месяц/сезон (например: "август", "15-22 июня")
- budget: бюджет в долларах (например: "2000", "до 1500")
- travelers: количество человек (число)
- tour_type: тип отдыха (например: "пляж", "экскурсии", "горы", "круиз")

Ответь строго JSON:
{
  "destination": null,
  "dates": null,
  "budget": null,
  "travelers": null,
  "tour_type": null,
  "missing_params": ["список отсутствующих параметров"]
}

Сообщение: {message}

Уже известные параметры: {known_params}
"""

CLARIFY_PROMPT = """Ты — дружелюбный туристический агент. Уточни у клиента {missing_param}.

Напиши одно короткое, естественное сообщение на русском языке с эмодзи.
Используй контекст предыдущих сообщений. Не перечисляй все параметры — спрашивай только одно.

Примеры:
- "Какой у вас бюджет на человека? 💰"
- "На сколько человек ищем тур? 👨‍👩‍👧‍👦"
- "Какой месяц планируете? 📅"
"""


async def clarify(state: DialogState) -> dict:
    """Извлекает параметры или задаёт уточняющий вопрос."""

    last_message = state["messages"][-1].content
    known = state.get("tour_params", {})

    llm = get_llm()
    response = await llm.ainvoke(
        EXTRACT_PROMPT.format(message=last_message, known_params=known)
    )
    result = json.loads(response.content)

    # Обновляем известные параметры
    updated_params = {**known}
    for key in ("destination", "dates", "budget", "travelers", "tour_type"):
        if result.get(key) is not None:
            updated_params[key] = result[key]

    missing = result.get("missing_params", [])

    if missing and len(state["messages"]) < 4:  # Максимум 3 цикла уточнения
        # Спрашиваем первый отсутствующий параметр
        clarify_response = await llm.ainvoke(
            CLARIFY_PROMPT.format(missing_param=missing[0])
        )
        return {
            "tour_params": updated_params,
            "current_step": "clarify",
            "awaiting_field": missing[0],
            "messages": [AIMessage(content=clarify_response.content)],
        }
    else:
        # Достаточно параметров — переходим к поиску
        return {
            "tour_params": updated_params,
            "current_step": "search",
        }
```

## Узел: Поиск туров (src/ai/tour_search.py)

```python
from src.services.google_sheets import GoogleSheetsService
from src.ai.states import DialogState


async def search_tours(state: DialogState) -> dict:
    """Ищет туры в Google Sheets по параметрам клиента."""

    params = state.get("tour_params", {})
    sheets = GoogleSheetsService()

    tours = await sheets.search_tours(
        destination=params.get("destination"),
        tour_type=params.get("tour_type"),
        budget=params.get("budget"),
        dates=params.get("dates"),
        travelers=params.get("travelers"),
    )

    return {"found_tours": tours}


async def present_tours(state: DialogState) -> dict:
    """Формирует ответ с найденными турами и ссылками."""

    tours = state.get("found_tours", [])

    if not tours:
        # Ничего не найдено → эскалация
        return {
            "needs_escalation": True,
            "escalation_reason": "Туры не найдены по заданным параметрам",
            "messages": [
                AIMessage(
                    content=(
                        "К сожалению, по вашим параметрам я не нашёл подходящих туров 😔\n"
                        "Но не переживайте! Я передам ваш запрос нашему менеджеру — "
                        "он подберёт для вас индивидуальный вариант. 🏖️"
                    )
                )
            ],
        }

    # Формируем красивый ответ
    lines = ["Вот что я нашёл для вас! 🌴\n"]
    for i, tour in enumerate(tours, 1):
        lines.append(
            f"**{i}. {tour['Название']}**\n"
            f"📍 {tour['Направление']} | 💰 {tour['Цена']}/чел | 📅 {tour['Даты']}\n"
            f"🔗 [Подробное описание]({tour['Ссылка']})\n"
        )
    lines.append(
        "\nХотите записаться на один из туров? 😊\n"
        "Или можете получить консультацию менеджера — просто напишите!"
    )

    return {
        "messages": [AIMessage(content="\n".join(lines))],
    }
```

## Узел: Эскалация (src/ai/nodes.py — escalate)

```python
from src.services.telegram_notify import TelegramNotifier


async def escalate(state: DialogState) -> dict:
    """Передаёт диалог живому менеджеру через Telegram-уведомление."""

    notifier = TelegramNotifier()
    await notifier.notify_manager(
        client_name=state.get("client_name", "Не указано"),
        client_phone=state.get("client_phone", "Не указан"),
        client_email=state.get("client_email", "Не указан"),
        request_summary=_summarize_request(state),
        conversation_history=state.get("conversation_history", []),
        tag=state.get("escalation_reason", "Нужен звонок"),
    )

    # Уведомляем клиента
    return {
        "messages": [
            AIMessage(
                content=(
                    "Я передал ваш запрос нашему менеджеру 📋\n"
                    "Он свяжется с вами в ближайшее время! 🤝\n"
                    "Обычно это занимает 15–30 минут в рабочее время."
                )
            )
        ]
    }


def _summarize_request(state: DialogState) -> str:
    """Формирует краткое описание запроса."""
    params = state.get("tour_params", {})
    parts = []
    if params.get("destination"):
        parts.append(f"Направление: {params['destination']}")
    if params.get("dates"):
        parts.append(f"Даты: {params['dates']}")
    if params.get("budget"):
        parts.append(f"Бюджет: {params['budget']}")
    return "; ".join(parts) if parts else state["messages"][-1].content
```

## Узел: Сбор контактов (src/ai/nodes.py — book)

```python
BOOK_PROMPT = """Ты — дружелюбный туристический агент. Собери у клиента контактные данные.

Текущий этап: {step}
Уже собрано: {collected}

Инструкции:
- Если step=NAME: попроси имя (приветливо)
- Если step=PHONE: попроси номер телефона (укажи формат +375...)
- Если step=EMAIL: попроси email
- Если step=CONFIRM: покажи собранные данные и попроси подтвердить

Одно сообщение. На русском. С эмодзи.
"""

import re


def validate_phone(phone: str) -> bool:
    """Валидация номера телефона (РБ / международный)."""
    return bool(re.match(r"\+375\d{9}", phone.replace("-", "").replace(" ", "")))


def validate_email(email: str) -> bool:
    """Валидация email."""
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


async def book(state: DialogState) -> dict:
    """Собирает контакты клиента для записи на тур."""

    step = state.get("current_step", "NAME")
    last_message = state["messages"][-1].content

    if step == "NAME":
        name = last_message.strip()
        return {
            "client_name": name,
            "current_step": "PHONE",
            "messages": [
                AIMessage(
                    content="Отлично, {name}! 📝 А ваш номер телефона? (формат: +375XX XXX XX XX)"
                )
            ],
        }

    elif step == "PHONE":
        phone = last_message.strip()
        if not validate_phone(phone):
            return {
                "messages": [
                    AIMessage(
                        content="Hmm, не совсем понял номер 🤔 Введите в формате +375XX XXX XX XX"
                    )
                ]
            }
        return {
            "client_phone": phone,
            "current_step": "EMAIL",
            "messages": [
                AIMessage(content="Спасибо! 📧 И последний штрих — ваш email для отправки деталей тура:")
            ],
        }

    elif step == "EMAIL":
        email = last_message.strip()
        if not validate_email(email):
            return {
                "messages": [
                    AIMessage(content="Неправильный формат email 😕 Попробуйте ещё раз:")
                ]
            }
        return {
            "client_email": email,
            "current_step": "CONFIRM",
            "messages": [
                AIMessage(
                    content=(
                        f"Проверьте данные ✅\n\n"
                        f"👤 Имя: {state['client_name']}\n"
                        f"📞 Телефон: {state['client_phone']}\n"
                        f"📧 Email: {email}\n"
                        f"🏖 Тур: {state.get('selected_tour', 'Не выбран')}\n\n"
                        f"Всё верно? Напишите «да» для подтверждения 🤝"
                    )
                )
            ],
        }

    elif step == "CONFIRM":
        if "да" in last_message.lower():
            # Сохраняем в Google Sheets
            sheets = GoogleSheetsService()
            await sheets.create_request(
                name=state["client_name"],
                phone=state["client_phone"],
                email=state["client_email"],
                tour=state.get("selected_tour", ""),
                destination=state.get("tour_params", {}).get("destination", ""),
                budget=state.get("tour_params", {}).get("budget", ""),
                travelers=state.get("tour_params", {}).get("travelers", 0),
            )
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "Отлично, заявка создана! 🎉\n"
                            "Наш менеджер свяжется с вами в ближайшее время для "
                            "подтверждения бронирования. Хорошего дня! ☀️"
                        )
                    )
                ]
            }
        else:
            return {
                "current_step": "NAME",
                "messages": [
                    AIMessage(content="Давайте начнём заново. Как вас зовут? 😊")
                ]
            }
```
