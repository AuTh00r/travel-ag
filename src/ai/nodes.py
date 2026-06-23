import json
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from structlog import get_logger

from src.ai.classifier import classify
from src.ai.prompts import (
    CLARIFY_PROMPT,
    EXTRACT_PROMPT,
    GREETING_PROMPT,
    PRESENT_TOURS_PROMPT,
    SELECT_TOUR_PROMPT,
    build_context,
)
from src.ai.states import DialogState
from src.ai.tour_search import search_tours
from src.config import settings
from src.db.sessions import save_booking_request
from src.services.google_sheets import GoogleSheetsService
from src.services.llm import get_llm, get_llm_json

_EXTRACT_NAME_PROMPT = """Извлеки имя пользователя из сообщения.

Сообщение: {message}

Ответь JSON: {{"name": "только имя, без лишних слов"}}

Если имя не удаётся определить, верни {{"name": null}}.
"""
from src.services.telegram_notify import TelegramNotifier

logger = get_logger()


async def greet(state: DialogState) -> dict:
    llm = get_llm()
    response = await llm.ainvoke([HumanMessage(content=GREETING_PROMPT)])
    return {
        "messages": [AIMessage(content=response.content)],
        "current_step": "greeting",
    }


async def classify_node(state: DialogState) -> dict:
    return await classify(state)


async def clarify(state: DialogState) -> dict:
    last_human = next(
        (m for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
        None,
    )
    if not last_human:
        return {
            "current_step": "search",
            "tour_params": state.get("tour_params", {}),
        }
    last_message = last_human.content
    known = state.get("tour_params", {})
    context = build_context(state["messages"])

    llm = get_llm_json()
    response = await llm.ainvoke(
        [
            HumanMessage(
                content=EXTRACT_PROMPT.format(
                    message=last_message,
                    known_params=json.dumps(known, ensure_ascii=False),
                    context=context,
                )
            )
        ]
    )
    try:
        result = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("clarify.json_parse_failed", raw=response.content)
        result = {}

    updated_params = {**known}
    for key in ("destination", "dates", "budget", "travelers", "tour_type"):
        if result.get(key) is not None:
            updated_params[key] = result[key]

    missing = result.get("missing_params", [])
    ai_msgs = [m for m in state["messages"] if not isinstance(m, HumanMessage)]
    should_clarify = bool(missing) and len(ai_msgs) < 3

    clarify_messages = []
    if should_clarify:
        llm = get_llm()
        clarify_response = await llm.ainvoke(
            [
                HumanMessage(
                    content=CLARIFY_PROMPT.format(
                        missing_param=missing[0], context=context
                    )
                )
            ]
        )
        clarify_messages = [AIMessage(content=clarify_response.content)]

    return {
        "tour_params": updated_params,
        "current_step": "clarify" if should_clarify else "search",
        "awaiting_field": missing[0] if missing else None,
        "messages": clarify_messages,
    }


async def search_tours_node(state: DialogState) -> dict:
    return await search_tours(state)


def _format_tour_for_presentation(index: int, t: dict) -> str:
    name = t.get("Название", "Тур")
    dest = t.get("Направление", "")
    price = t.get("Цена", "")
    dates = t.get("Даты", "")
    duration = t.get("Длительность", "")
    link = t.get("Ссылка", "")
    tour_type = t.get("Тип", "")
    parts = [f"[Тур {index}]"]
    parts.append(f"Название: {name}")
    if dest:
        parts.append(f"Направление: {dest}")
    if tour_type:
        parts.append(f"Тип: {tour_type}")
    if dates:
        parts.append(f"Даты: {dates}")
    if price:
        parts.append(f"Цена: {price}")
    if duration:
        parts.append(f"Длительность: {duration}")
    if link:
        parts.append(f"Ссылка: {link}")
    return "\n".join(parts)


async def present_tours(state: DialogState) -> dict:
    tours = state.get("found_tours", [])

    if not tours:
        return {
            "needs_escalation": True,
            "escalation_reason": "Туры не найдены по заданным параметрам",
        }

    context = build_context(state["messages"])

    tours_text = "\n\n".join(
        _format_tour_for_presentation(i + 1, t) for i, t in enumerate(tours)
    )

    llm = get_llm()
    response = await llm.ainvoke(
        [
            HumanMessage(
                content=PRESENT_TOURS_PROMPT.format(
                    tours=tours_text, context=context
                )
            )
        ]
    )

    return {
        "current_step": "awaiting_selection",
        "messages": [AIMessage(content=response.content)],
    }


def validate_phone(phone: str) -> bool:
    return bool(re.match(r"\+375\d{9}", phone.replace("-", "").replace(" ", "")))


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[^@]+@[^@]+\.[^@]+$", email))


def _build_confirm_text(state: DialogState) -> str:
    params = state.get("tour_params", {})
    selected = state.get("selected_tour")
    tour_line = ""
    if selected:
        tour_line = "\n\U0001f3d7\ufe0f \u0422\u0443\u0440: " + selected
    extras = ""
    if params.get("destination"):
        extras += (
            "\n\U0001f30d \u041d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u0438\u0435: "
            + params["destination"]
        )
    if params.get("dates"):
        extras += "\n\U0001f4c5 \u0414\u0430\u0442\u044b: " + params["dates"]
    return (
        "\u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 \u0434\u0430\u043d\u043d\u044b\u0435 \u2705\n\n"
        "\U0001f464 \u0418\u043c\u044f: " + (state.get("client_name", "") or "") + "\n"
        "\U0001f4de \u0422\u0435\u043b\u0435\u0444\u043e\u043d: "
        + (state.get("client_phone", "") or "")
        + "\n"
        "\U0001f4e7 Email: "
        + (state.get("client_email", "") or "")
        + extras
        + tour_line
        + "\n\n\u0412\u0441\u0451 \u0432\u0435\u0440\u043d\u043e? \u041d\u0430\u043f\u0438\u0448\u0438\u0442\u0435 \u00ab\u0434\u0430\u00bb \u0434\u043b\u044f \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u0438\u044f \U0001f91d"
    )


async def book(state: DialogState) -> dict:
    step = state.get("current_step", "ASK_NAME")
    last_message = state["messages"][-1].content

    if step == "ASK_NAME":
        return {
            "current_step": "AWAIT_NAME",
            "messages": [AIMessage(content="Давайте познакомимся! Как вас зовут? 😊")],
        }

    if step == "AWAIT_NAME":
        try:
            llm = get_llm_json()
            name_response = await llm.ainvoke(
                [HumanMessage(content=_EXTRACT_NAME_PROMPT.format(message=last_message))]
            )
            name_result = json.loads(name_response.content)
            raw_name = name_result.get("name")
            name = raw_name.strip() if isinstance(raw_name, str) else ""
        except (json.JSONDecodeError, TypeError):
            name = last_message.strip()

        if not name or len(name) < 2:
            return {
                "current_step": "AWAIT_NAME",
                "messages": [
                    AIMessage(content="Не расслышал, повторите имя, пожалуйста 🙏")
                ],
            }
        return {
            "client_name": name,
            "current_step": "AWAIT_PHONE",
            "messages": [
                AIMessage(
                    content=f"Приятно познакомиться, {name}! 📝 А ваш номер телефона? (формат: +375XX XXX XX XX)"
                )
            ],
        }

    if step == "AWAIT_PHONE":
        phone = last_message.strip()
        if not validate_phone(phone):
            return {
                "current_step": "AWAIT_PHONE",
                "messages": [
                    AIMessage(
                        content="Не совсем понял номер 🤔 Введи в формате +375XX XXX XX XX, пожалуйста:"
                    )
                ],
            }
        return {
            "client_phone": phone,
            "current_step": "AWAIT_EMAIL",
            "messages": [
                AIMessage(
                    content="Спасибо! 📧 И последний штрих — ваш email для отправки деталей тура:"
                )
            ],
        }

    if step == "AWAIT_EMAIL":
        email = last_message.strip()
        if not validate_email(email):
            return {
                "current_step": "AWAIT_EMAIL",
                "messages": [
                    AIMessage(
                        content="Неправильный формат email 😕 Попробуйте ещё раз:"
                    )
                ],
            }
        return {
            "client_email": email,
            "current_step": "CONFIRM",
            "messages": [
                AIMessage(content=_build_confirm_text(state)),
            ],
        }

    if step == "CONFIRM":
        if "да" in last_message.lower():
            sheets = GoogleSheetsService()
            await sheets.create_request(
                name=state.get("client_name", ""),
                phone=state.get("client_phone", ""),
                email=state.get("client_email", ""),
                tour=state.get("selected_tour", ""),
                destination=state.get("tour_params", {}).get("destination", ""),
                budget=state.get("tour_params", {}).get("budget", ""),
                travelers=state.get("tour_params", {}).get("travelers", 1),
            )
            await save_booking_request(
                client_id=state.get("client_id", ""),
                name=state.get("client_name", ""),
                phone=state.get("client_phone", ""),
                email=state.get("client_email", ""),
                tour=state.get("selected_tour", ""),
                destination=state.get("tour_params", {}).get("destination", ""),
                budget=state.get("tour_params", {}).get("budget", ""),
                travelers=state.get("tour_params", {}).get("travelers", 1),
            )
            booking_link = ""
            if settings.booking_form_url:
                booking_link = (
                    f"\n\n\U0001f4e6 Вы также можете забронировать онлайн по ссылке:\n"
                    f"{settings.booking_form_url}"
                )

            return {
                "current_step": "COMPLETED",
                "messages": [
                    AIMessage(
                        content="Отлично, заявка создана! 🎉\n"
                        "Наш менеджер свяжется с вами в ближайшее время для "
                        "подтверждения бронирования."
                        + booking_link
                        + "\n\nХорошего дня! ☀️"
                    )
                ],
            }
        else:
            return {
                "current_step": "ASK_NAME",
                "messages": [
                    AIMessage(content="Давайте начнём заново. Как вас зовут? 😊")
                ],
            }

    return {}


async def handle_tour_selection(state: DialogState) -> dict:
    tours = state.get("found_tours", [])
    last_message = state["messages"][-1].content if state["messages"] else ""

    context = build_context(state["messages"])
    tours_text = "\n\n".join(
        _format_tour_for_presentation(i + 1, t) for i, t in enumerate(tours)
    )
    llm = get_llm_json()

    try:
        response = await llm.ainvoke(
            [
                HumanMessage(
                    content=SELECT_TOUR_PROMPT.format(
                        tours=tours_text, message=last_message, context=context
                    )
                )
            ]
        )
        result = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        result = {"action": "ask_again", "reply": "Не совсем понял вас 😊 Можете уточнить, какой тур интересует?"}

    action = result.get("action", "ask_again")
    reply = result.get("reply", "Не совсем понял вас 😊")

    if action == "select":
        idx = result.get("selected_tour_index")
        if idx is not None and 1 <= idx <= len(tours):
            selected_name = result.get("selected_tour_name") or tours[idx - 1].get("Название", f"Тур {idx}")
            return {
                "selected_tour": selected_name,
                "current_step": "ASK_NAME",
                "messages": [AIMessage(content=reply)],
            }
        return {
            "current_step": "awaiting_selection",
            "messages": [AIMessage(content=reply)],
        }

    if action == "retry":
        return {
            "current_step": "clarify",
            "tour_params": {},
            "found_tours": [],
            "selected_tour": None,
            "messages": [AIMessage(content=reply)],
        }

    if action == "escalate":
        return {
            "needs_escalation": True,
            "escalation_reason": "Клиент отклонил все туры",
            "current_step": "awaiting_selection",
            "messages": [AIMessage(content=reply)],
        }

    return {
        "current_step": "awaiting_selection",
        "messages": [AIMessage(content=reply)],
    }


def _summarize_request(state: DialogState) -> str:
    params = state.get("tour_params", {})
    parts = []
    if params.get("destination"):
        parts.append(f"\U0001f30d Направление: {params['destination']}")
    if params.get("dates"):
        parts.append(f"\U0001f4c5 Даты: {params['dates']}")
    if params.get("budget"):
        parts.append(f"\U0001f4b0 Бюджет: {params['budget']}")
    if params.get("travelers"):
        parts.append(f"\U0001f465 Человек: {params['travelers']}")
    if params.get("tour_type"):
        parts.append(f"\U0001f3d6 Тип: {params['tour_type']}")
    selected = state.get("selected_tour")
    if selected:
        parts.append(f"\U0001f3d7 Тур: {selected}")
    if parts:
        return "\n".join(parts)
    return state["messages"][-1].content if state.get("messages") else "Не указан"


async def escalate(state: DialogState) -> dict:
    conversation_history = state.get("conversation_history", [])
    if not conversation_history:
        conversation_history = [
            {
                "role": "user" if isinstance(m, HumanMessage) else "assistant",
                "text": m.content,
            }
            for m in state.get("messages", [])
            if hasattr(m, "content")
        ][-20:]

    notifier = TelegramNotifier()
    try:
        await notifier.notify_manager(
            client_name=state.get("client_name") or "Не указано",
            client_phone=state.get("client_phone") or "Не указан",
            client_email=state.get("client_email") or "Не указан",
            request_summary=_summarize_request(state),
            conversation_history=conversation_history,
            tag=state.get("escalation_reason") or "Нужен звонок",
        )
    except Exception as exc:
        logger.error("telegram.notification.failed", error=str(exc))

    reason = state.get("escalation_reason")
    if reason and "не найдены" in reason:
        user_msg = (
            "К сожалению, по вашим параметрам я не нашёл подходящих туров 😔\n"
            "Я передал ваш запрос нашему менеджеру — "
            "он подберёт для вас индивидуальный вариант. 🏖️"
        )
    else:
        user_msg = (
            "Я передал ваш запрос нашему менеджеру 📋\n"
            "Он свяжется с вами в ближайшее время! 🤝\n"
            "Обычно это занимает 15–30 минут в рабочее время."
        )

    return {
        "conversation_history": conversation_history,
        "messages": [AIMessage(content=user_msg)],
    }
