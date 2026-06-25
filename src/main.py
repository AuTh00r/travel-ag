import asyncio
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response
from pydantic import BaseModel
from structlog import get_logger

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.db.sessions import (
    get_requests_by_client,
    get_session,
    is_manager_active,
    save_booking_request,
    save_session,
    update_request_status,
)
from src.services.google_sheets import GoogleSheetsService

logger = get_logger()

instagram = InstagramChannel()

# Время последнего POST-запроса от Meta на webhook (для быстрой диагностики
# без чтения логов; in-memory, не персистентно между рестартами).
_last_webhook_at: datetime | None = None

# Активные фоновые задачи обработки сообщений. Meta ретраит вебхук, если
# не получает 200 быстро, а LLM-обработка идёт ~50 сек — поэтому отвечаем
# 200 мгновенно, а обработку пускаем в фоне. Сет нужен, чтобы asyncio не
# garbage-collect-нул задачу, на которую никто не держит ссылку.
_background_tasks: set[asyncio.Task] = set()

# Дедупликация входящих webhook'ов по message_id. Meta ретраит один и тот
# же webhook при network blip или рестарте приложения — без дедупа каждое
# сообщение может быть обработано 2-3 раза. In-memory, сбрасывается при
# рестарте (достаточно, т.к. Meta ретраит только первые несколько секунд).
_processed_mids: set[str] = set()
_PROCESSED_MIDS_MAX = 10_000  # ограничение размера сета

# Локи для сериализации обработки сообщений одного клиента.
# Предотвращает гонку: два сообщения от одного пользователя не должны
# обрабатываться параллельно (иначе оба читают одну сессию и дублируют ответ).
_locks: dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.db.faq_db import load_faq_to_chroma
    from src.services.tour_loader import load_tours

    def _load_faq():
        try:
            count = load_faq_to_chroma()
            logger.info("faq.ready", entries=count)
        except Exception:
            logger.exception("faq.load_failed")

    def _load_tours():
        try:
            tours_text = load_tours()
            app.state.tours_text = tours_text
            logger.info("tours.ready", chars=len(tours_text))
        except Exception:
            logger.exception("tours.load_failed")
            app.state.tours_text = ""

    threading.Thread(target=_load_faq, daemon=True).start()
    threading.Thread(target=_load_tours, daemon=True).start()
    yield


app = FastAPI(
    title="Travel Agent Bot",
    description="ИИ-помощник турагентства",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "ok"}


# --- API управления заявками ---


class StatusUpdateRequest(BaseModel):
    status: str


REQUEST_STATUSES = {"Новая", "В обработке", "Подтверждена", "Оплачена"}


@app.get("/api/requests/{client_id}")
async def get_client_requests(client_id: str):
    requests = await get_requests_by_client(client_id)
    if not requests:
        raise HTTPException(status_code=404, detail="Заявки не найдены")
    return {"client_id": client_id, "requests": requests}


@app.patch("/api/requests/{client_id}/status")
async def update_request_status_endpoint(client_id: str, body: StatusUpdateRequest):
    if body.status not in REQUEST_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Неверный статус. Допустимые: {', '.join(sorted(REQUEST_STATUSES))}",
        )

    # Обновить в SQLite
    updated = await update_request_status(client_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    # Попробовать обновить в Google Sheets (best-effort)
    try:
        requests_data = await get_requests_by_client(client_id)
        if requests_data:
            req = requests_data[0]
            sheets = GoogleSheetsService()
            await sheets.update_request_status(
                name=req.get("name", ""),
                phone=req.get("phone", ""),
                new_status=body.status,
            )
    except Exception:
        logger.exception("google_sheets.status_update_failed", client_id=client_id)

    return {"client_id": client_id, "status": body.status, "updated": True}


@app.get("/webhook/instagram")
async def verify_instagram_webhook(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
):
    return await instagram.verify_webhook(hub_mode, hub_challenge, hub_verify_token)


@app.get("/webhook/instagram/last_seen")
async def webhook_last_seen():
    """Быстрая диагностика: достукивается ли Meta до webhook.

    Возвращает время последнего POST от Meta. Если `received_ever=False`,
    значит POST вообще не приходил (часто = приложение не в Live Mode
    и пользователь не в App Roles). in-memory, сбрасывается при рестарте.
    """
    return {
        "received_ever": _last_webhook_at is not None,
        "last_received_at": _last_webhook_at.isoformat() if _last_webhook_at else None,
    }


async def _get_lock(sender_id: str) -> asyncio.Lock:
    async with _locks_lock:
        if sender_id not in _locks:
            _locks[sender_id] = asyncio.Lock()
        return _locks[sender_id]


_BOOKING_RE = re.compile(
    r"===БРОНЬ===\s*\n(.*?)\n===БРОНЬ===", re.DOTALL
)
_ESCALATION_RE = re.compile(
    r"===МЕНЕДЖЕР===\s*\n(.*?)\n===МЕНЕДЖЕР===", re.DOTALL
)


def _extract_booking(text: str) -> dict | None:
    m = _BOOKING_RE.search(text)
    if not m:
        return None
    data = {}
    for line in m.group(1).strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            data[key.strip().lower()] = val.strip()
    if not data.get("имя") or not data.get("телефон"):
        return None
    return {
        "name": data.get("имя", ""),
        "phone": data.get("телефон", ""),
        "email": data.get("email", ""),
        "tour": data.get("тур", ""),
    }


def _extract_escalation(text: str) -> tuple[str, str] | None:
    """Парсит ===МЕНЕДЖЕР=== и возвращает (причина, контекст).

    Контекст опционален — если не заполнен, дублирует причину.
    Если маркера нет — None.
    """
    m = _ESCALATION_RE.search(text)
    if not m:
        return None
    reason = ""
    context = ""
    for line in m.group(1).strip().split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key_s = key.strip().lower()
        if key_s == "причина":
            reason = val.strip()
        elif key_s == "контекст":
            context = val.strip()
    if not reason:
        reason = m.group(1).strip()
    return reason, context or reason


def _strip_markers(text: str) -> str:
    text = _BOOKING_RE.sub("", text)
    text = _ESCALATION_RE.sub("", text)
    return text.strip()


def _guard_reply(reason: str) -> str:
    replies = {
        "too_long": "Сообщение слишком длинное. Напишите покороче — я обязательно помогу 😊",
        "injection": "Я могу помочь только с вопросами о наших турах 😊",
    }
    return replies.get(reason, "Не понял вопрос. Попробуйте переформулировать!")


async def process_with_ai(sender_id: str, text: str) -> None:
    from src.ai.prompts import build_full_prompt
    from src.db.faq_db import search_faq
    from src.services.guard import check_input, check_output, is_rate_limited
    from src.services.llm import get_llm
    from src.services.telegram_notify import TelegramNotifier
    from src.services.tour_loader import get_tours_text

    # Пауза: если живой менеджер недавно писал в этот чат — бот молчит.
    pre = await get_session(sender_id)
    if is_manager_active(pre, settings.manager_takeover_ttl_minutes):
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            if is_manager_active(session, settings.manager_takeover_ttl_minutes):
                history = session.get("history", [])
                history.append({"role": "user", "content": text})
                session["history"] = history
                await save_session(sender_id, session)
                logger.info("manager.active.skip_llm", sender_id=sender_id)
                return

    if is_rate_limited(sender_id):
        logger.warning("guard.rate_limited", sender_id=sender_id)
        await instagram.send_message(
            sender_id,
            "Вы пишете слишком часто. Пожалуйста, подождите минуту 🙏",
        )
        return

    ok, reason = check_input(text)
    if not ok:
        logger.warning("guard.input_rejected", sender_id=sender_id, reason=reason)
        await instagram.send_message(sender_id, _guard_reply(reason))
        return

    lock = await _get_lock(sender_id)
    async with lock:
        session = await get_session(sender_id)
        history = session.get("history", [])

        tours_text = get_tours_text()

        faq_context = ""
        try:
            relevant = await search_faq(text)
            if relevant:
                faq_context = "\n\n".join(
                    e["document"] for e in relevant[:3]
                )
        except Exception:
            logger.debug("faq.search_skipped")

        instagram_handle = await instagram.get_username(sender_id)

        escalation_count = session.get("escalation_count", 0)
        messages = build_full_prompt(tours_text, faq_context, history, text, escalation_count)

        llm = get_llm()
        response = await llm.ainvoke(messages)
        raw_reply = response.content

        booking_data = _extract_booking(raw_reply)
        extracted = _extract_escalation(raw_reply)
        escalation_reason, escalation_context = extracted if extracted else (None, None)

        if "===БРОНЬ" in raw_reply and not booking_data:
            logger.warning("marker.parse_failed", marker_type="booking", snippet=raw_reply[-500:])
        if "===МЕНЕДЖЕР" in raw_reply and not extracted:
            logger.warning("marker.parse_failed", marker_type="escalation", snippet=raw_reply[-500:])

        clean_reply = _strip_markers(raw_reply)
        clean_reply = check_output(clean_reply)

        if booking_data:
            try:
                sheets = GoogleSheetsService()
                await sheets.create_request(**booking_data)
                logger.info("booking.created", **booking_data)
            except Exception:
                logger.exception("booking.create_failed")

            try:
                await save_booking_request(
                    client_id=sender_id,
                    **booking_data,
                )
            except Exception:
                logger.exception("booking.db_save_failed")

        if escalation_reason:
            if escalation_count >= 3:
                logger.info("escalation.limit_reached", sender_id=sender_id, count=escalation_count)
            else:
                try:
                    notifier = TelegramNotifier()
                    await notifier.notify_manager(
                        sender_id=sender_id,
                        instagram_handle=instagram_handle,
                        context=escalation_context,
                        client_name=(booking_data or {}).get("name"),
                        client_phone=(booking_data or {}).get("phone"),
                        client_email=(booking_data or {}).get("email"),
                        tag="Нужен звонок",
                    )
                    escalation_count += 1
                except Exception:
                    logger.exception("escalation.notify_failed")

        history.append({"role": "user", "content": text})
        history.append({"role": "assistant", "content": clean_reply})
        session["history"] = history
        session["escalation_count"] = escalation_count
        await save_session(sender_id, session)

        try:
            await instagram.send_message(sender_id, clean_reply)
        except Exception:
            logger.exception("instagram.message.send_failed", sender_id=sender_id)


async def _mark_manager_active(client_id: str, manager_text: str) -> None:
    """Живой менеджер ответил клиенту — ставим/продлеваем паузу бота."""
    try:
        lock = await _get_lock(client_id)
        async with lock:
            session = await get_session(client_id)
            session["manager_last_at"] = datetime.now(timezone.utc).isoformat()
            if manager_text:
                history = session.get("history", [])
                history.append({"role": "assistant", "content": manager_text})
                session["history"] = history
            await save_session(client_id, session)
        logger.info("manager.takeover", client_id=client_id)
    except Exception:
        logger.exception("manager.takeover.failed", client_id=client_id)


async def _process_safely(sender_id: str, text: str) -> None:
    """Фоновая обработка сообщения.

    Запускается через asyncio.create_task после немедленного ответа 200 Meta.
    Логирует свои ошибки, т.к. request-контекст уже закрыт.
    """
    try:
        await process_with_ai(sender_id, text)
    except Exception:
        logger.exception("ai.processing.failed", sender_id=sender_id)
        try:
            await instagram.send_message(
                sender_id,
                "Произошла техническая ошибка. "
                "Наши специалисты уже работают над этим. Попробуйте позже! 🛠️",
            )
        except Exception:
            logger.exception("instagram.message.send_failed", sender_id=sender_id)


@app.post("/webhook/instagram")
async def receive_instagram_message(request: Request):
    global _last_webhook_at

    raw_body = await request.body()
    # Фиксируем факт обращения ДО проверки подписи — так даже невалидные
    # запросы отразятся в last_seen (полезно при диагностике Live/Dev mode).
    _last_webhook_at = datetime.now(timezone.utc)

    sig = request.headers.get("X-Hub-Signature-256")
    if not instagram.verify_signature(raw_body, sig):
        logger.warning("instagram.webhook.invalid_signature")
        return Response(status_code=403, content="Invalid signature")

    payload = await request.json()
    events = await instagram.receive_message(payload)
    logger.info("instagram.webhook.received", events=len(events))

    # Запускаем обработку в фоне и отвечаем Meta 200 мгновенно.
    for ev in events:
        mid = ev.get("mid", "")
        if mid:
            if mid in _processed_mids:
                logger.info("instagram.webhook.dedup_skipped", mid=mid)
                continue
            _processed_mids.add(mid)
            if len(_processed_mids) > _PROCESSED_MIDS_MAX:
                excess = len(_processed_mids) - _PROCESSED_MIDS_MAX
                for _ in range(excess):
                    _processed_mids.pop()
        else:
            logger.warning("instagram.message.no_mid", kind=ev.get("kind"))
            continue

        if ev["kind"] == "manager":
            task = asyncio.create_task(
                _mark_manager_active(ev["client_id"], ev.get("text", ""))
            )
        else:  # "user"
            logger.info("instagram.message.processing", sender_id=ev["sender_id"])
            task = asyncio.create_task(_process_safely(ev["sender_id"], ev["text"]))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return Response(status_code=200, content="")
