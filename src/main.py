import asyncio
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from structlog import get_logger

from src.channels.instagram import InstagramChannel
from src.config import settings
from src.db.pending_messages import (
    delete_pending,
    enqueue_pending,
    get_due_pending,
    mark_pending_retry,
)
from src.db.sessions import (
    get_session,
    is_manager_active,
    save_session,
)
from src.exceptions import InstagramRateLimitError
from src.logging_config import configure_logging

configure_logging()

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

# Meta присылает shared post и текст в отдельных POST-запросах (~2s apart).
# _in_ai_processing фиксирует sender_id, для которого запущена AI-обработка.
# _process_non_text_safely проверяет этот dict и пропускает auto-ack,
# если AI уже отвечает или скоро ответит.
_in_ai_processing: dict[str, float] = {}
_AI_PROCESSING_TTL = 30.0  # секунд


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

    # Фоновый воркер очереди недоставленных сообщений
    worker_task = asyncio.create_task(_pending_messages_worker())
    _background_tasks.add(worker_task)
    worker_task.add_done_callback(_background_tasks.discard)

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


_PRIVACY_POLICY_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Privacy Policy — Sandita Travel Agency</title></head>
<body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.5;">
<h1>Privacy Policy — Sandita Travel Agency</h1>
<p>Last updated: July 9, 2026</p>
<p>Sandita ("we", "our") operates an Instagram Direct Message assistant for our
travel agency (Minsk, Belarus, ul. K. Liebknechta 66, office 608) to help
customers with questions about tours, prices, and bookings.</p>

<h2>What information we collect</h2>
<ul>
<li>The content of your Instagram Direct Messages to our account</li>
<li>Your Instagram username/name, retrieved via the Instagram API</li>
<li>Your phone number and/or email address, only if you voluntarily provide
them to request a booking</li>
</ul>

<h2>How we use this information</h2>
<ul>
<li>To generate automated replies to your questions using an AI language model</li>
<li>To match your questions against our tour catalog and FAQ</li>
<li>To forward your request to a human staff member when a booking is
requested or your question requires personal attention</li>
</ul>

<h2>Who we share it with</h2>
<ul>
<li>DeepSeek, our AI language model provider, receives message text to
generate a reply</li>
<li>Our internal staff (via a private Telegram channel) receive your contact
details and message context when a booking or escalation occurs</li>
<li>We do not sell your data or share it with advertisers</li>
</ul>

<h2>How long we keep it</h2>
<p>Conversation history is stored on our own server for as long as needed to
provide support, until you request deletion (see
<a href="/data-deletion">Data Deletion Instructions</a>).</p>

<h2>Your rights</h2>
<p>You may request access to or deletion of your data at any time — see
<a href="/data-deletion">Data Deletion Instructions</a>, or contact us
directly.</p>

<h2>Contact</h2>
<p>Sandita Travel Agency, Minsk, ul. K. Liebknechta 66, office 608<br>
Email: sundita.minsk@gmail.com<br>
Phone: +375 29 356 83 24 / +375 29 152 37 28</p>
</body>
</html>"""

_DATA_DELETION_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Data Deletion Instructions — Sandita Travel Agency</title></head>
<body style="font-family: sans-serif; max-width: 700px; margin: 40px auto; line-height: 1.5;">
<h1>Data Deletion Instructions — Sandita Travel Agency</h1>
<p>To request deletion of your data collected through our Instagram Direct
assistant:</p>
<ol>
<li>Send a message to our Instagram account (the same one you messaged)
stating you want your data deleted, or</li>
<li>Email us at sundita.minsk@gmail.com or call us at
+375 29 356 83 24 / +375 29 152 37 28</li>
</ol>
<p>We will remove your conversation history and any contact details we stored
within 7 business days and confirm once complete.</p>
<p>See also our <a href="/privacy">Privacy Policy</a>.</p>
</body>
</html>"""


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    return _PRIVACY_POLICY_HTML


@app.get("/data-deletion", response_class=HTMLResponse)
async def data_deletion_instructions():
    return _DATA_DELETION_HTML


@app.post("/api/admin/reset-takeover/{client_id}")
async def reset_takeover(client_id: str):
    """Сбросить паузу бота для клиента — бот снова отвечает."""
    try:
        session = await get_session(client_id)
        if session.get("manager_last_at") is None:
            return {"client_id": client_id, "reset": False, "reason": "already_active"}
        session["manager_last_at"] = None
        await save_session(client_id, session)
        logger.info("admin.reset_takeover", client_id=client_id)
        return {"client_id": client_id, "reset": True}
    except Exception:
        logger.exception("admin.reset_takeover.failed", client_id=client_id)
        raise HTTPException(status_code=500, detail="Internal server error")


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


_ESCALATION_RE = re.compile(
    r"===МЕНЕДЖЕР===\s*\n(.*?)\n===МЕНЕДЖЕР===", re.DOTALL
)


def _extract_escalation(text: str) -> dict | None:
    """Парсит ===МЕНЕДЖЕР=== и возвращает dict с ключами reason, context, name, phone.

    Если маркера нет — None.
    """
    m = _ESCALATION_RE.search(text)
    if not m:
        return None
    result: dict[str, str] = {}
    for line in m.group(1).strip().split("\n"):
        if ":" not in line:
            continue
        key, val = line.split(":", 1)
        key_s = key.strip().lower()
        if key_s == "причина":
            result["reason"] = val.strip()
        elif key_s == "контекст":
            result["context"] = val.strip()
        elif key_s == "имя":
            result["name"] = val.strip()
        elif key_s == "телефон":
            result["phone"] = val.strip()
    if not result.get("reason"):
        result["reason"] = m.group(1).strip()
    result.setdefault("context", result["reason"])
    return result


_TEXT_FORMATTING_RE = re.compile(r"\*{1,2}(.+?)\*{1,2}")


def _strip_markers(text: str) -> str:
    text = _ESCALATION_RE.sub("", text)
    text = _TEXT_FORMATTING_RE.sub(r"\1", text)
    return text.strip()


def _split_reply(text: str, max_len: int = 1000) -> list[str]:
    """Разбить ответ на части по границам предложений."""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while len(text) > max_len:
        candidate = text[:max_len]
        split_at = -1
        for sep in (". ", "! ", "? ", "\n\n", "\n"):
            pos = candidate.rfind(sep)
            if pos > split_at:
                split_at = pos + len(sep)
        if split_at <= 0:
            split_at = max_len
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()
    if text:
        chunks.append(text)
    return chunks


def _guard_reply(reason: str) -> str:
    replies = {
        "too_long": "Сообщение слишком длинное. Напишите покороче — я обязательно помогу 😊",
        "injection": "Я могу помочь только с вопросами о наших турах 😊",
    }
    return replies.get(reason, "Не понял вопрос. Попробуйте переформулировать!")


def _should_greet(prev_last_iso: str | None, is_first: bool) -> tuple[bool, bool]:
    """Определяет флаги приветствия.

    Возвращает (should_greet, is_first_message).
    - Первое сообщение в сессии → приветствуем, это первое сообщение.
    - Возврат после паузы ≥12ч → приветствуем, НО не первое сообщение (имя не спрашиваем).
    - Продолжение диалога (<12ч) → не приветствуем.
    """
    if is_first:
        return True, True
    if prev_last_iso is None:
        return True, False
    try:
        ts = datetime.fromisoformat(prev_last_iso)
    except (ValueError, TypeError):
        return True, True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    hours_since = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
    if hours_since >= 12:
        return True, False
    return False, False


async def _send_or_queue(sender_id: str, text: str) -> tuple[bool, str | None]:
    """Отправить сообщение клиенту; при сбое поставить в очередь на повтор.

    Возвращает (True, None) при успехе. При провале сообщение уже поставлено
    в pending_messages, возвращает (False, retry_at) — retry_at можно
    переиспользовать, если нужно поставить в очередь ещё несколько сообщений
    с тем же временем повтора (см. process_with_ai — остальные chunks одного
    ответа не пытаемся отправлять, раз этот уже словил лимит).
    """
    try:
        await instagram.send_message(sender_id, text)
        return True, None
    except InstagramRateLimitError as exc:
        logger.warning("instagram.message.send_failed", sender_id=sender_id)
        logger.error(
            "instagram.message.lost",
            sender_id=sender_id,
            reason="rate_limited",
            error_code=exc.error_code,
            retry_after_seconds=exc.retry_after_seconds,
        )
        retry_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=exc.retry_after_seconds or settings.default_retry_seconds)
        ).isoformat()
        await enqueue_pending(sender_id, text, retry_at)
        return False, retry_at
    except Exception:
        logger.exception("instagram.message.send_failed", sender_id=sender_id)
        logger.error("instagram.message.lost", sender_id=sender_id, reason="other")
        retry_at = (
            datetime.now(timezone.utc) + timedelta(seconds=settings.default_retry_seconds)
        ).isoformat()
        await enqueue_pending(sender_id, text, retry_at)
        return False, retry_at


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
                logger.info("manager.active.skip_llm", sender_id=sender_id)
                return

    if is_rate_limited(sender_id):
        logger.warning("guard.rate_limited", sender_id=sender_id)
        await _send_or_queue(
            sender_id,
            "Вы пишете слишком часто. Пожалуйста, подождите минуту 🙏",
        )
        return

    ok, reason = check_input(text)
    if not ok:
        logger.warning("guard.input_rejected", sender_id=sender_id, reason=reason)
        await _send_or_queue(sender_id, _guard_reply(reason))
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
        from src.config import MINSK_TZ
        now_minsk = datetime.now(MINSK_TZ)
        current_time = now_minsk.strftime("%H:%M")
        current_date = now_minsk.date()
        is_first = not history
        should_greet, is_first_msg = _should_greet(
            session.get("last_message_at"), is_first,
        )
        messages = build_full_prompt(
            tours_text, faq_context, history, text, escalation_count,
            current_date=current_date,
            current_time=current_time,
            should_greet=should_greet,
            is_first_message=is_first_msg,
        )

        llm = get_llm()
        response = await llm.ainvoke(messages)
        raw_reply = response.content

        escalation_data = _extract_escalation(raw_reply)
        escalation_reason = (escalation_data or {}).get("reason")
        escalation_context = (escalation_data or {}).get("context")
        escalation_name = (escalation_data or {}).get("name")
        escalation_phone = (escalation_data or {}).get("phone")

        if "===МЕНЕДЖЕР" in raw_reply and not escalation_data:
            logger.warning("marker.parse_failed", marker_type="escalation", snippet=raw_reply[-500:])

        clean_reply = _strip_markers(raw_reply)
        clean_reply = check_output(clean_reply)

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
                        client_name=escalation_name,
                        client_phone=escalation_phone,
                        tag="Нужен звонок",
                    )
                    escalation_count += 1
                except Exception:
                    logger.exception("escalation.notify_failed")

        # Сохраняем user-реплику, НО НЕ assistant — её сохраним только после
        # успешной отправки, чтобы история не врала о недоставленном ответе.
        history.append({"role": "user", "content": text})
        session["history"] = history
        session["escalation_count"] = escalation_count
        session["last_message_at"] = datetime.now(timezone.utc).isoformat()
        await save_session(sender_id, session)

        # Пытаемся отправить все chunks. В историю попадает только реально
        # доставленное — если chunk N упал, chunks[N:] не пытаемся отправлять
        # (тот же сбой), а сразу ставим в очередь с тем же retry_at. Успешно
        # отправленные до сбоя chunks (sent_chunks) всё равно фиксируем в
        # истории — иначе клиент получил кусок ответа, а бот об этом не помнит.
        chunks = _split_reply(clean_reply)
        sent_chunks: list[str] = []
        for i, chunk in enumerate(chunks):
            ok, retry_at = await _send_or_queue(sender_id, chunk)
            if not ok:
                for remaining in chunks[i + 1:]:
                    await enqueue_pending(sender_id, remaining, retry_at)
                break
            sent_chunks.append(chunk)

        if sent_chunks:
            history.append({"role": "assistant", "content": " ".join(sent_chunks)})
            session["history"] = history
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)


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


async def _process_non_text_safely(sender_id: str, text: str, metadata: dict) -> None:
    """Обработка non-text сообщения (вложение, shared post, story reply).

    Не вызывает LLM. Передаёт информацию менеджеру через Telegram
    и отвечает клиенту acknowledgement с задержкой, чтобы не дублировать
    AI-ответ, если Meta пришлёт текст отдельным POST-запросом.
    """
    try:
        from src.services.telegram_notify import TelegramNotifier

        # 1. Manager takeover gate
        pre = await get_session(sender_id)
        if is_manager_active(pre, settings.manager_takeover_ttl_minutes):
            lock = await _get_lock(sender_id)
            async with lock:
                session = await get_session(sender_id)
                if is_manager_active(session, settings.manager_takeover_ttl_minutes):
                    logger.info("manager.active.skip_non_text", sender_id=sender_id)
                    return

        # 2. Per-user lock — эскалация и сохранение сессии
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            instagram_handle = await instagram.get_username(sender_id)
            escalation_count = session.get("escalation_count", 0)
            summary = metadata.get("summary", "неизвестный тип")

            if escalation_count < 3:
                context_msg = (
                    f"Клиент отправил не текстовое сообщение в Instagram.\n"
                    f"Тип: {summary}\n"
                    f"Текст клиента: {text or 'без текста'}\n"
                    f"Бот не видит содержимое вложения/поста/истории."
                )
                try:
                    notifier = TelegramNotifier()
                    await notifier.notify_manager(
                        sender_id=sender_id,
                        instagram_handle=instagram_handle,
                        context=context_msg,
                        tag="Non-text",
                    )
                    escalation_count += 1
                    logger.info(
                        "instagram.non_text.escalated",
                        sender_id=sender_id,
                        types=metadata.get("types"),
                    )
                except Exception:
                    logger.exception(
                        "instagram.non_text.notify_failed",
                        sender_id=sender_id,
                    )
                client_reply = (
                    "Спасибо! Я не вижу содержимое вложения, "
                    "поэтому передал ваш вопрос менеджеру.\n"
                    "Он посмотрит и поможет 🙌"
                )
            else:
                logger.info(
                    "instagram.non_text.escalation_skipped_limit",
                    sender_id=sender_id,
                    count=escalation_count,
                )
                client_reply = (
                    "Ваш запрос уже передан менеджеру, "
                    "ожидайте, пожалуйста. Он свяжется с вами в ближайшее время."
                )

            # 3. Сохранить историю БЕЗ реплики ассистента — её добавим
            #    только после успешной отправки.
            history = session.get("history", [])
            history.append(
                {
                    "role": "user",
                    "content": f"[Instagram non-text] {summary}. "
                    f"Текст клиента: {text or 'без текста'}",
                }
            )
            session["history"] = history
            session["escalation_count"] = escalation_count
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)

        # 4. Локальная блокировка отпущена.
        #    Ждём немного: если появилась AI-обработка от того же sender'а,
        #    auto-ack не отправляем (AI ответит и без нас).
        import time as _time

        await asyncio.sleep(5)
        now = _time.monotonic()
        if sender_id in _in_ai_processing and now - _in_ai_processing.get(sender_id, 0) < _AI_PROCESSING_TTL:
            logger.info(
                "instagram.non_text.ack_skipped_ai_pending",
                sender_id=sender_id,
            )
            return

        # 5. Ответить клиенту
        ok, _ = await _send_or_queue(sender_id, client_reply)
        if not ok:
            return

        # Отправлено успешно — добавляем реплику ассистента в историю
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            history = session.get("history", [])
            history.append({"role": "assistant", "content": client_reply})
            session["history"] = history
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)
    except Exception:
        logger.exception("instagram.non_text.processing.failed", sender_id=sender_id)
        fallback_text = (
            "Произошла техническая ошибка. "
            "Наши специалисты уже работают над этим. Попробуйте позже! 🛠️"
        )
        await _send_or_queue(sender_id, fallback_text)


async def _process_safely(sender_id: str, text: str) -> None:
    """Фоновая обработка сообщения.

    Запускается через asyncio.create_task после немедленного ответа 200 Meta.
    Логирует свои ошибки, т.к. request-контекст уже закрыт.
    """
    try:
        await process_with_ai(sender_id, text)
    except Exception:
        logger.exception("ai.processing.failed", sender_id=sender_id)
        fallback_text = (
            "Произошла техническая ошибка. "
            "Наши специалисты уже работают над этим. Попробуйте позже! 🛠️"
        )
        await _send_or_queue(sender_id, fallback_text)


async def _reschedule_or_giveup(row: dict, retry_after_seconds: float | None) -> None:
    """Перепланировать недоставленное сообщение или сдаться после MAX_ATTEMPTS.

    Если попытки исчерпаны — удаляем из очереди, логируем
    instagram.message.giveup и эскалируем в Telegram (Задача 5).
    """
    delay = retry_after_seconds or settings.default_retry_seconds
    new_retry_at = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()

    # row["attempts"] считает только повторные попытки ВОРКЕРА — самая первая
    # (неудачная) отправка в process_with_ai/_process_non_text_safely/
    # _process_safely в этот счётчик не попадает, там сообщение сразу
    # уходит в очередь с attempts=0. Значит на момент этой проверки реально
    # уже было (row["attempts"] + 2) попыток: 1 изначальная + row["attempts"]
    # уже учтённых воркером + 1 текущая (только что провалившаяся, ещё не
    # записанная). Сдаёмся, когда это суммарное число достигнет
    # max_retry_attempts — отсюда порог `max_retry_attempts - 2`.
    total_attempts_so_far = row["attempts"] + 2
    if total_attempts_so_far >= settings.max_retry_attempts:
        await delete_pending(row["id"])
        logger.error(
            "instagram.message.giveup",
            recipient_id=row["recipient_id"],
            attempts=total_attempts_so_far,
        )
        from src.services.telegram_notify import TelegramNotifier
        try:
            notifier = TelegramNotifier()
            await notifier.notify_manager(
                sender_id=row["recipient_id"],
                context=(
                    f"Не удалось доставить сообщение клиенту "
                    f"{row['recipient_id']} после {total_attempts_so_far} попыток "
                    f"— Instagram API недоступен/лимит. Ответьте вручную."
                ),
                tag="Сбой доставки",
            )
        except Exception:
            logger.exception("instagram.message.giveup.notify_failed")
    else:
        await mark_pending_retry(row["id"], new_retry_at)


async def _pending_messages_worker():
    """Фоновый воркер, досылающий сообщения из очереди pending_messages.

    Запускается в lifespan как asyncio.create_task. Опрашивает очередь
    каждые pending_worker_interval_seconds, отправляет due-сообщения
    (с per-user блокировкой, чтобы не было гонки с обычной обработкой).
    """
    while True:
        await asyncio.sleep(settings.pending_worker_interval_seconds)
        due = await get_due_pending(datetime.now(timezone.utc).isoformat())
        for row in due:
            lock = await _get_lock(row["recipient_id"])
            async with lock:
                try:
                    await instagram.send_message(row["recipient_id"], row["text"])
                    # Дослано успешно — добавляем в историю сессии
                    session = await get_session(row["recipient_id"])
                    history = session.get("history", [])
                    history.append({"role": "assistant", "content": row["text"]})
                    session["history"] = history
                    session["last_message_at"] = datetime.now(timezone.utc).isoformat()
                    await save_session(row["recipient_id"], session)
                    await delete_pending(row["id"])
                    logger.info(
                        "pending.resent",
                        id=row["id"],
                        recipient_id=row["recipient_id"],
                    )
                except InstagramRateLimitError as exc:
                    await _reschedule_or_giveup(row, exc.retry_after_seconds)
                except Exception:
                    logger.exception("pending.send_failed", id=row["id"])
                    await _reschedule_or_giveup(row, None)


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
    # Сначала отмечаем sender'ов, для которых будет AI-обработка.
    # Это нужно, чтобы _process_non_text_safely мог пропустить auto-ack,
    # если AI уже обрабатывает текст клиента.
    import time as _time
    for ev in events:
        if ev["kind"] in ("user", "user_non_text") and ev.get("text"):
            _in_ai_processing[ev["sender_id"]] = _time.monotonic()

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
        elif ev["kind"] == "user_non_text":
            nt_text = ev.get("text", "")
            nt_types = ev.get("non_text", {}).get("types", [])
            if nt_text:
                nt_summary = ev.get("non_text", {}).get("summary", "")
                augmented = f"{nt_text}\n\n[Клиент также отправил: {nt_summary}]"
                logger.info(
                    "instagram.non_text.with_text",
                    sender_id=ev["sender_id"],
                    types=nt_types,
                )
                task = asyncio.create_task(_process_safely(ev["sender_id"], augmented))
            else:
                logger.info(
                    "instagram.non_text.processing",
                    sender_id=ev["sender_id"],
                    types=nt_types,
                )
                task = asyncio.create_task(
                    _process_non_text_safely(
                        ev["sender_id"],
                        "",
                        ev.get("non_text", {}),
                    )
                )
        else:  # "user"
            logger.info("instagram.message.processing", sender_id=ev["sender_id"])
            task = asyncio.create_task(_process_safely(ev["sender_id"], ev["text"]))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return Response(status_code=200, content="")
