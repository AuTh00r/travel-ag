import json
import re

from langchain_core.messages import AIMessage, HumanMessage
from structlog import get_logger

from src.ai.prompts import CONVERSE_PROMPT, PRESENT_TOURS_PROMPT, build_context
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


async def converse(state: DialogState) -> dict:
    llm = get_llm_json()

    context = build_context(state["messages"])
    tour_params = state.get("tour_params", {})
    found_tours = state.get("found_tours", [])

    tours_text = ""
    if found_tours:
        tours_lines = []
        for i, t in enumerate(found_tours, 1):
            name = t.get("Название", "Тур")
            dest = t.get("Направление", "")
            price = t.get("Цена", "")
            tours_lines.append(f"[{i}] {name} — {dest} — {price}")
        tours_text = "\n".join(tours_lines)

    prompt = CONVERSE_PROMPT.format(
        context=context,
        tour_params=json.dumps(tour_params, ensure_ascii=False) if tour_params else "нет",
        tours=tours_text if tours_text else "нет",
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    try:
        result = json.loads(response.content)
    except (json.JSONDecodeError, TypeError):
        logger.warning("converse.json_parse_failed", raw=response.content)
        result = {"action": "respond", "reply": "Извините, я не совсем понял. Можете повторить? 😊"}

    action = result.get("action", "respond")
    reply = result.get("reply", "")
    new_params = result.get("tour_params")
    selected_tour = result.get("selected_tour")

    updates: dict = {
        "messages": [AIMessage(content=reply)],
        "next_action": action,
    }

    if new_params and isinstance(new_params, dict):
        merged = dict(tour_params)
        for k, v in new_params.items():
            if v is not None:
                merged[k] = v
        if "budget" in merged and not isinstance(merged["budget"], str):
            merged["budget"] = str(merged["budget"])
        if "travelers" in merged and not isinstance(merged["travelers"], int):
            merged["travelers"] = int(merged["travelers"])
        if merged != tour_params:
            updates["tour_params"] = merged

    if selected_tour:
        updates["selected_tour"] = selected_tour

    if action == "book":
        if state.get("current_step") not in ("AWAIT_NAME", "AWAIT_PHONE", "AWAIT_EMAIL", "CONFIRM"):
            updates["current_step"] = "ASK_NAME"

    return updates


async def search_tours_node(state: DialogState) -> dict:
    return await search_tours(state)


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
        [HumanMessage(content=PRESENT_TOURS_PROMPT.format(tours=tours_text, context=context))]
    )

    return {
        "current_step": "awaiting_selection",
        "messages": [AIMessage(content=response.content)],
    }


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
