import asyncio
import hmac
import hashlib
import json
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import uuid4

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from structlog import get_logger

from src.channels.instagram import InstagramChannel, _MidSet, _normalize_phone, text_only_ad_event
from src.config import settings
from src.db.pending_messages import (
    delete_pending,
    enqueue_pending,
    get_due_pending,
    mark_pending_retry,
)
from src.db.inbound import StaleWork
from src.db.sessions import (
    effective_escalation_count,
    get_session,
    is_manager_active,
    save_session,
    trim_history,
)
from src.exceptions import InstagramRateLimitError, StoryMediaError, VoiceMediaError
from src.logging_config import configure_logging
from src.services.llm_response_log import catalog_metadata, log_llm_response
from src.services.handoff_review import HandoffDecision, review_manager_candidate
from src.services.diagnostic_trace import error_details, log_inbound, log_model_request, trace_event, trace_scope, traced_flow
from src.services.meta_diagnostics import webhook_rejection_fields
from src.services.inbound_recovery import RecoveryService, current_processing, legacy_processing, mark_processing
from src.services.model_failure import CALL_TIMEOUTS, retryable_error

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
#
# _MidSet, а не обычный set: set.pop() удаляет произвольный элемент по хешу,
# а не самый старый (проверено — вылетали и mid_000, и mid_013 вперемешку).
# При переполнении из защиты мог выпасть свежий mid, и переприсланный Meta
# вебхук обрабатывался повторно — клиент получал ответ дважды.
_processed_mids: _MidSet = _MidSet()
_PROCESSED_MIDS_MAX = 10_000  # ограничение размера сета

# Локи для сериализации обработки сообщений одного клиента.
# Предотвращает гонку: два сообщения от одного пользователя не должны
# обрабатываться параллельно (иначе оба читают одну сессию и дублируют ответ).
_locks: dict[str, asyncio.Lock] = {}
_locks_lock = asyncio.Lock()
_processing_locks: dict[str, asyncio.Lock] = {}
_manager_pending: dict[str, int] = {}
_INBOUND_WAIT_SECONDS = 5.0
_inbound_batches: dict[str, list[dict]] = {}
_inbound_tasks: dict[str, asyncio.Task] = {}
_inbound_locks: dict[str, asyncio.Lock] = {}
_STORY_REACTION_TTL_SECONDS = 600.0
_STORY_REACTIONS_MAX = 10_000
_story_reactions: dict[str, tuple[float, dict]] = {}
_STORY_UNAVAILABLE = (
    "Не удалось прочитать эту историю. Подскажите, пожалуйста, название тура "
    "или напишите нужные сведения из истории — тогда смогу ответить на ваш вопрос."
)
_IMAGE_NO_CAPTION = "[Изображение без подписи]"
_IMAGE_UNAVAILABLE = (
    "Не удалось прочитать изображение. Пришлите его ещё раз в формате JPEG или PNG "
    "или напишите название тура и ваш вопрос текстом."
)
_POST_NO_QUESTION = "[Публикация без вопроса]"
_POST_UNAVAILABLE = (
    "Не удалось получить содержимое этой публикации или Reels. "
    "Пришлите исходное фото/видео либо напишите название тура и ваш вопрос текстом."
)
_AD_UNAVAILABLE = (
    "Не удалось получить содержимое рекламы. Подскажите название тура или пришлите "
    "фото/видео объявления, чтобы мы могли уточнить детали."
)

_SHARED_POST_CLARIFICATION = (
    "Подскажите, пожалуйста, что именно вас заинтересовало в публикации: "
    "название тура, направление, даты или стоимость?"
)

# Флаг: первичная загрузка базы туров (DOCX + первая попытка sync) завершена.
# Воркер синхронизации ждёт его перед первым тиком, чтобы не гоняться
# с `_load_tours` за память и снапшот-файл.
_tours_initial_loaded = threading.Event()


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
        # Поверх локальной базы — свежая версия из Drive, если настроено.
        # В отдельном потоке и так, сеть старту бота не тормозит.
        # Событие — СТРОГО ПОСЛЕ начальной синхронизации: воркер, стартовавший
        # раньше, увидел бы отсутствие снапшота и посчитал бы это первым
        # запуском (прод-кейс 2026-10-04).
        try:
            _initial_tour_sync()
        except Exception:
            logger.exception("tour_sync.initial_failed")
        finally:
            _tours_initial_loaded.set()

    threading.Thread(target=_load_faq, daemon=True).start()
    threading.Thread(target=_load_tours, daemon=True).start()

    from src.db.manager_tasks import recover_legacy_intents
    recover_legacy_intents()

    # Фоновый воркер очереди недоставленных сообщений
    worker_task = asyncio.create_task(_pending_messages_worker())
    _background_tasks.add(worker_task)
    worker_task.add_done_callback(_background_tasks.discard)

    manager_worker = asyncio.create_task(_manager_notifications_worker())
    _background_tasks.add(manager_worker)
    manager_worker.add_done_callback(_background_tasks.discard)

    if settings.inbound_recovery_enabled:
        recovery = _get_recovery()
        recovery_task = asyncio.create_task(recovery.run())
        _background_tasks.add(recovery_task)
        recovery_task.add_done_callback(_background_tasks.discard)
        if settings.instagram_reconcile_enabled:
            scanner_task = asyncio.create_task(recovery.reconcile_loop())
            _background_tasks.add(scanner_task)
            scanner_task.add_done_callback(_background_tasks.discard)

    # Фоновый воркер синхронизации туров из Google Drive
    sync_task = asyncio.create_task(_tour_sync_worker())
    _background_tasks.add(sync_task)
    sync_task.add_done_callback(_background_tasks.discard)

    if settings.ads_media_enabled:
        app.state.ads_media_status = {"enabled": True, "ready": False}
        async def check_ads():
            from src.services.ad_media import check_ad_access
            try:
                app.state.ads_media_status = await check_ad_access()
                logger.info("ad.media.access_ready")
            except StoryMediaError as exc:
                app.state.ads_media_status = {"enabled": True, "ready": False, "reason": str(exc)}
                logger.warning("ad.media.access_failed", reason=str(exc))
            except Exception:
                app.state.ads_media_status = {"enabled": True, "ready": False, "reason": "ad_check_failed"}
                logger.warning("ad.media.access_failed", reason="ad_check_failed")
        ads_task = asyncio.create_task(check_ads())
        _background_tasks.add(ads_task)
        ads_task.add_done_callback(_background_tasks.discard)

    try:
        yield
    finally:
        tasks = list(_background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        from src.services.voice_media import close_voice_worker
        await close_voice_worker()
        _inbound_batches.clear()
        _inbound_tasks.clear()
        _story_reactions.clear()


app = FastAPI(
    title="Travel Agent Bot",
    description="ИИ-помощник турагентства",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    result = {"status": "ok"}
    if settings.deepseek_tool_scope == 'all':
        result['model_tools'] = {'enabled': True, 'scope': 'all'}
    elif settings.tool_clients():
        result['model_tools'] = {'enabled': True, 'scope': 'allowlist', 'client_count': len(settings.tool_clients())}
    if settings.ads_media_enabled:
        result["ads_media"] = getattr(app.state, "ads_media_status", {"enabled": True, "ready": False})
    if settings.inbound_recovery_enabled:
        result["inbound_recovery"] = {"enabled": True, "reconcile_enabled": settings.instagram_reconcile_enabled}
    return result


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


def _require_admin_token(provided: str | None) -> None:
    """Пустить дальше только с верным X-Admin-Token.

    Роут доступен из интернета через Cloudflare Tunnel и пишет в сессию
    (снимает паузу бота), поэтому знания client_id недостаточно: это обычный
    Instagram sender_id, он светится в Telegram-уведомлениях и логах.

    Пока токен не настроен — 404, а не «пускаем всех»: пустое поле в .env не
    должно молча открывать доступ. 404 вместо 401 и здесь, и при неверном
    токене — чтобы снаружи нельзя было отличить «роут есть, но токен не тот»
    от «роута нет».
    """
    expected = settings.admin_api_token
    if not expected:
        logger.warning("admin.auth.token_not_configured")
        raise HTTPException(status_code=404, detail="Not Found")
    # Сравниваем байты, а не строки: compare_digest на str с не-ASCII символами
    # бросает TypeError (проверено), и такой заголовок дал бы 500 вместо 404.
    if not provided or not hmac.compare_digest(
        provided.encode("utf-8", "surrogatepass"),
        expected.encode("utf-8", "surrogatepass"),
    ):
        logger.warning("admin.auth.rejected")
        raise HTTPException(status_code=404, detail="Not Found")


@app.post("/api/admin/reset-takeover/{client_id}")
async def reset_takeover(
    client_id: str,
    x_admin_token: str | None = Header(default=None, alias="X-Admin-Token"),
):
    """Сбросить паузу бота для клиента — бот снова отвечает."""
    _require_admin_token(x_admin_token)
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
    r"={2,}[ \t]*МЕНЕДЖЕР[ \t]*=*[ \t]*\r?\n(.*?)"
    r"(?:\r?\n={2,}[ \t]*МЕНЕДЖЕР[ \t]*=*[ \t]*|$)", re.DOTALL | re.IGNORECASE
)
_SERVICE_HEADER_RE = re.compile(r"={2,}[ \t]*МЕНЕДЖЕР\b[ \t]*=*", re.IGNORECASE)


_TEXT_FORMATTING_RE = re.compile(r"\*{1,2}(.+?)\*{1,2}")


def _has_contact_phone(text: str, known_numbers: set[str]) -> bool:
    for number in known_numbers:
        forms = [number.lstrip("+")]
        if number.startswith("+375") and len(number) == 13:
            forms.append("80" + number[4:])
        for digits in forms:
            pattern = r"(?<![0-9])\+?" + r"[ ()\u00a0-]*".join(digits) + r"(?![0-9])"
            if re.search(pattern, text):
                return True
    for match in re.finditer(r"(?<!\w)\+?[0-9][0-9 ()\u00a0-]{5,30}(?!\w)", text):
        number = _normalize_phone(match.group())
        if match.group().lstrip().startswith("+") and len(re.sub(r"\D", "", match.group())) >= 7:
            return True
        if number and (match.group().lstrip().startswith("+") or number.startswith("+375")
                or number in known_numbers):
            return True
    return False


def _strip_markers(text: str) -> str:
    text = _ESCALATION_RE.sub("", text)
    # Даже обрезанный заголовок без body/закрывающей строки не идёт клиенту.
    text = _SERVICE_HEADER_RE.split(text, maxsplit=1)[0]
    text = _TEXT_FORMATTING_RE.sub(r"\1", text)
    return text.strip()


_HANDOFF_LIMIT_REPLY = (
    "Новое уведомление менеджеру не отправлено: достигнут лимит повторных обращений. "
    "Вы можете связаться с менеджерами напрямую."
)
_HANDOFF_FAILED_REPLY = (
    "Не удалось подтвердить передачу нового обращения менеджеру. "
    "Пожалуйста, повторите сообщение позже или свяжитесь с менеджерами напрямую."
)
_HANDOFF_ACTION_RE = re.compile(
    r"\b(?:переда(?:л[аи]?|ли|ю|м|ём|ем|н\w*|ст\w*|д[иу]м)|перенаправ\w*|"
    r"переадрес\w*|отправ(?:ил\w*|лен\w*|ляю)|направ(?:ил\w*|лен\w*|ляю)|"
    r"уведом(?:ил\w*|лен\w*|ляю)|получ(?:ил[аи]?|ен[аоы]?))\b", re.IGNORECASE,
)
_HANDOFF_STAFF_RE = re.compile(r"\b(?:менеджер\w*|специалист\w*|сотрудник\w*|наталь\w*|татьян\w*)\b",
                              re.IGNORECASE)
_HANDOFF_TARGET_RE = re.compile(
    r"\b(?:менеджер\w*|специалист\w*|сотрудник\w*|наталь\w*|татьян\w*|"
    r"запрос\w*|контакт\w*|обращени\w*|вопрос\w*|номер\w*)\b", re.IGNORECASE,
)
_HANDOFF_CALLBACK_RE = re.compile(
    r"\b(?:менеджер\w*|специалист\w*|он|они)\b.{0,100}\b(?:свяж\w*|перезвон\w*|позвон\w*)\b|"
    r"\b(?:свяж\w*|перезвон\w*|позвон\w*)\b.{0,100}\b(?:менеджер\w*|специалист\w*)\b|"
    r"^\s*(?:с вами\s+)?(?:скоро\s+)?(?:свяжутся|перезвонят)\b|"
    r"^\s*с вами\s+(?:скоро\s+)?(?:свяжется|перезвонит)\b",
    re.IGNORECASE,
)


def _finalize_handoff_reply(reply: str, outcome: str, *, limited: bool = False,
                            outside_hours: bool = False) -> str:
    """Model prose is not a receipt; append only the actual notification outcome."""
    kept, removed = [], False
    for part in re.split(r"(?<=[.!?])(?=\s)|(?<=\n)", reply):
        kept_clauses = []
        part_removed = False
        for clause in re.split(r"(?<=[,;—–])(?=\s)", part):
            if clause.rstrip().endswith("?"):
                kept_clauses.append(clause)
                continue
            claim = False
            for action in _HANDOFF_ACTION_RE.finditer(clause):
                target = _HANDOFF_STAFF_RE if action[0].casefold().startswith("получ") else _HANDOFF_TARGET_RE
                negated = (re.search(r"\bне\s+(?:(?:был\w*|будет|ещ[её]|уже)\s+){0,2}$",
                                     clause[:action.start()], re.IGNORECASE)
                           or re.match(r"\s+не\b", clause[action.end():], re.IGNORECASE))
                if target.search(clause) and (outcome != "none" or not negated):
                    claim = True
            callback = _HANDOFF_CALLBACK_RE.search(clause)
            if outcome == "none" and re.search(r"\bне\s+(?:свяж\w*|перезвон\w*|позвон\w*)", clause, re.IGNORECASE):
                callback = None
            if claim or callback:
                part_removed = removed = True
            else:
                kept_clauses.append(clause)
        remaining = "".join(kept_clauses)
        if part_removed:
            remaining = remaining.rstrip(" \t,;—–")
            if (remaining.strip() and part.rstrip().endswith(".") and not remaining.endswith(".")
                    and not re.search(r"https?://\S+$", remaining)):
                remaining += "."
        kept.append(remaining)
    if outcome == "none" and not removed:
        return reply
    if outcome == "none" and limited:
        outcome = "limit"
    receipt = {
        "sent": "Ваш запрос передан менеджеру.",
        "failed": _HANDOFF_FAILED_REPLY,
        "limit": _HANDOFF_LIMIT_REPLY,
        "none": "Новое уведомление менеджеру не отправлено. Вы можете связаться с менеджерами напрямую.",
        "deferred": "",
    }[outcome]
    if outcome == "sent" and outside_hours:
        receipt += " Менеджер ответит в рабочее время с 10:00 до 18:00."
    clean = re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()
    footer = re.search(r"(?m)^[ \t]*Наши менеджеры\b", clean)
    if footer:
        return "\n\n".join(part for part in (clean[:footer.start()].strip(), receipt,
                                             clean[footer.start():].strip()) if part)
    return "\n\n".join(part for part in (clean, receipt) if part)


def _human_media_context(text: str, known_numbers: set[str]) -> str:
    """Humanize notification provenance; leave persisted history unchanged."""
    text = _strip_markers(text)
    text = re.sub(r"https?://\S+|www\.\S+", "", text, flags=re.IGNORECASE)
    text = text.replace(_IMAGE_NO_CAPTION, "Клиент прислал фото/видео без подписи.")
    text = text.replace(_POST_NO_QUESTION, "Клиент прислал публикацию/Reels без вопроса.")
    text = re.sub(r"\[Ответ на историю [0-9]{1,32}, (IMAGE|VIDEO)\]",
                  lambda match: "[Вопрос по " + ("фотоистории" if match[1] == "IMAGE" else "видеоистории") + "]", text)
    replacements = (
        (r"\[Изображений: [0-9]+\]", "[Фото/видео клиента]"),
        (r"\[Story mention: изображения [0-9, ]+\]", "[Упоминание аккаунта в истории клиента]"),
        (r"\[Видео: вложения [0-9, ]+; по 10 кадров, без звука\]", "[Видеосообщение клиента, без звука]"),
        (r"\[Публикация/Reels, медиа обработано\]", "[Вопрос по публикации или Reels]"),
        (r"\[Публикация/Reels, медиа недоступно\]", "[Публикация или Reels недоступны боту]"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text)
    return "\n".join(line for line in text.splitlines()
                     if not _has_contact_phone(line, known_numbers)).strip()


def _ad_context(referral: dict | None) -> str:
    if not referral or referral.get("source") != "ADS":
        return ""
    title = referral.get("ad_title")
    title = re.sub(r"https?://\S+|www\.\S+", "", title).strip()[:500] if isinstance(title, str) else ""
    return "[Отклик на рекламу" + (": " + title if title else "; заголовок недоступен") + "]"


def _ad_visual_parts(referral: dict | None) -> list[dict]:
    if not referral or referral.get("source") != "ADS":
        return []
    if settings.ads_media_enabled and isinstance(referral.get("ad_id"), str):
        part = {"kind": "ad", "id": referral["ad_id"]}
        if settings.shared_media_enabled and (referral.get("post_id") or referral.get("permalink")):
            part["sources"] = [{"id": referral.get("post_id"), "url": referral.get("permalink")}]
        if settings.image_media_enabled:
            # Meta documents video_url as a thumbnail, not a full video source.
            url = referral.get("photo_url")
            if url:
                part.update(urls=[url], types=["image"])
        return [part]
    if settings.shared_media_enabled and (referral.get("post_id") or referral.get("permalink")):
        return [{"kind": "shared", "sources": [{"id": referral.get("post_id"),
                                                   "url": referral.get("permalink")}]}]
    if settings.image_media_enabled:
        url = referral.get("photo_url")
        if url:
            return [{"kind": "images", "urls": [url], "types": ["image"]}]
    return []


def _validate_response(raw: object, *, allow_silent: bool = False) -> tuple[dict | None, str | None]:
    """Validate the same strict envelope for every model route."""
    if not isinstance(raw, str):
        return None, "invalid_type"
    if len(raw) > 16000:
        return None, "response_too_long"
    raw = raw.strip()
    if not raw:
        return None, "empty_response"
    fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", raw, re.IGNORECASE | re.DOTALL)
    if fence:
        raw = fence[1]
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_fields")
            result[key] = value
        return result
    try:
        result = json.loads(raw, object_pairs_hook=unique_fields)
    except (json.JSONDecodeError, RecursionError):
        return None, "invalid_json"
    except ValueError:
        return None, "duplicate_fields"
    if not isinstance(result, dict) or set(result) != {"reply", "manager"}:
        return None, "invalid_fields"
    if not isinstance(result['reply'], str):
        return None, "invalid_field_type"
    manager = result['manager']
    if manager is not None:
        if not isinstance(manager, dict):
            return None, 'invalid_field_type'
        if set(manager) != {'context', 'type', 'name'}:
            return None, 'invalid_fields'
        if any(not isinstance(value, str) for value in manager.values()):
            return None, 'invalid_field_type'
        if manager['type'] not in {'консультация', 'контакт', 'отзыв'}:
            return None, 'invalid_manager_type'
        if len(manager['context']) > 450:
            return None, 'context_too_long'
        if not manager['context'].strip():
            return None, 'empty_context'
        if len(manager['name']) > 100:
            return None, 'name_too_long'
    if not result['reply'].strip() and (manager is None or not allow_silent):
        return None, "empty_reply"
    if _SERVICE_HEADER_RE.search(result['reply']) or re.search(r'={2,}\s*БРОНЬ\b', result['reply'], re.IGNORECASE):
        return None, 'service_marker'
    return result, None


def _response_metadata(response: object) -> dict:
    from src.services.llm import response_log_content
    raw = response_log_content(response)
    metadata = getattr(response, "response_metadata", None)
    finish = metadata.get("finish_reason") if isinstance(metadata, dict) else None
    finish = finish if isinstance(finish, str) and finish in {
        "stop", "length", "content_filter", "tool_calls", "function_call", "insufficient_system_resource"
    } else "unknown"
    usage = getattr(response, "usage_metadata", None)
    fields = {"finish_reason": finish, "response_chars": len(raw) if isinstance(raw, str) else None,
              "response_kind": "text" if isinstance(raw, str) else "other"}
    for key in ("input_tokens", "output_tokens"):
        value = usage.get(key) if isinstance(usage, dict) else None
        fields[key] = value if type(value) is int and 0 <= value <= 1_000_000_000 else None
    return fields


async def _technical_handoff(sender_id, text, reason, request_id, attempts, *, handle=None):
    """No client reply. The durable Telegram outbox owns delivery retries."""
    from src.services.model_failure import technical_context
    from src.services.telegram_notify import TelegramNotifier

    session = await get_session(sender_id)
    if _manager_pending.get(sender_id) or is_manager_active(session, settings.manager_takeover_ttl_minutes):
        mark_processing('manager_cancelled', 'manager_takeover')
        return
    mark_processing('failed_final', reason)
    history = session.setdefault('history', [])
    history.append({'role': 'user', 'content': text})
    session['last_message_at'] = datetime.now(timezone.utc).isoformat()
    await save_session(sender_id, session)
    context = technical_context(text, reason, request_id, attempts)
    processing = current_processing.get()
    if processing is not None:
        processing.technical_diagnostic = context
    trace_event('technical_handoff', sender_id=sender_id, request_id=request_id,
                reason=reason, attempts=attempts, context=context)
    try:
        await TelegramNotifier().notify_manager(sender_id=sender_id, instagram_handle=handle,
            context=context, client_phone=_input_phone_from_text(text),
            tag='техническая ошибка', decision=HandoffDecision({}, action='technical'))
    except StaleWork:
        raise
    except Exception as exc:
        # Committed operations retry independently; a planning failure is logged
        # too, and recovery prepares a replacement plan before committing final.
        logger.warning('technical.notification.failed', request_id=request_id, **error_details(exc))
        trace_event('technical_notification_failed', sender_id=sender_id, request_id=request_id, **error_details(exc))


async def _processing_failure(sender_id, text, reason, exc):
    request_id = uuid4().hex
    details = dict(attempt=0, stage='processing', reason=reason, **error_details(exc))
    logger.warning('ai.processing.failed', sender_id=sender_id, request_id=request_id, **details)
    trace_event('processing_error', sender_id=sender_id, request_id=request_id, **details)
    await _technical_handoff(sender_id, text, reason, request_id, [details])


def _brief_context(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit - 1].rsplit(" ", 1)[0] + "…"


def _valid_manager_context(context: str | None, known_numbers: set[str]) -> bool:
    return bool(context and context.strip() and len(context) <= 450
        and not _has_contact_phone(context, known_numbers)
        and not re.search(r"https?://|www\.|[0-9]{14,}|\[|===|\b(?:IMAGE|VIDEO)\b", context, re.IGNORECASE))


def _contact_escalation_context(current_question: str, history: list[dict], known_numbers: set[str],
        intro: str = "Клиент оставил номер телефона для связи.") -> str:
    context = intro
    candidates = [(-1, {"role": "user", "content": current_question}), *reversed(list(enumerate(history)))]
    for index, entry in candidates:
        previous = entry.get("content", "")
        if (entry.get("role") != "user" or not isinstance(previous, str) or not previous.strip()
                or _normalize_phone(previous)
                or "Номер в телефонной карточке: " in previous
                or _has_contact_phone(previous, known_numbers)):
            continue
        question = _human_media_context(previous, known_numbers)
        context += " Запрос: " + _brief_context(question, 200)
        if index >= 0:
            for following in history[index + 1:]:
                if following.get("role") == "user":
                    break
                if following.get("role") != "assistant" or not isinstance(following.get("content"), str):
                    continue
                reply = _human_media_context(following["content"], known_numbers)
                sentences = re.split(r"(?<=[.!?])\s+|\n+", reply)
                substantive = next((sentence.strip() for sentence in sentences
                    if sentence.strip() and not re.fullmatch(
                        r"(?:Ссылка\b[^:]*|Подробнее|Программа тура):\s*", sentence.strip(), re.IGNORECASE)
                    and not re.match(
                        r"^(?:Здравствуйте|Привет|Добрый (?:день|вечер)|Спасибо|Хорошо|"
                        r"Наши менеджеры|Я передал|Ваш запрос|Передал|Наталья и Татьяна)\b",
                        sentence.strip(), re.IGNORECASE)), None)
                if substantive:
                    context += " По разговору: " + _brief_context(substantive, 160)
                    break
        break
    return _brief_context(context, 450)


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
    processing = current_processing.get()
    trace_event('reply_prepared' if processing else 'reply_attempt', sender_id=sender_id,
                reply=text, delivery_deferred=processing is not None)
    if processing is not None and processing.client_id == sender_id:
        processing.plan_reply(text)
        return False, None  # Explicitly deferred: do not append assistant history.
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
    except Exception as exc:
        if getattr(exc, "journal_intent", None) and getattr(exc, "delivery_status", None) == "unknown":
            logger.error("inbound.legacy_delivery.unknown")
            return False, None
        logger.exception("instagram.message.send_failed", sender_id=sender_id)
        logger.error("instagram.message.lost", sender_id=sender_id, reason="other")
        retry_at = (
            datetime.now(timezone.utc) + timedelta(seconds=settings.default_retry_seconds)
        ).isoformat()
        await enqueue_pending(sender_id, text, retry_at)
        return False, retry_at


@traced_flow('processing')
async def process_with_ai(
    sender_id: str, text: str, story: dict | None = None,
    image_urls: list[object] | None = None,
    shared_sources: list[dict] | None = None,
    image_types: list[str] | None = None,
    voice_parts: list[dict] | None = None,
    visual_parts: list[dict] | None = None,
    referral: dict | None = None,
) -> None:
    # Сохраняем порядок вопросов, но освобождаем session lock на время декодирования.
    lock = _processing_locks.setdefault(sender_id, asyncio.Lock())
    async with lock:
        await _process_with_ai(sender_id, text, story, image_urls, shared_sources, image_types,
                               voice_parts, visual_parts, referral)


async def _process_with_ai(
    sender_id: str, text: str, story: dict | None = None,
    image_urls: list[object] | None = None,
    shared_sources: list[dict] | None = None,
    image_types: list[str] | None = None,
    voice_parts: list[dict] | None = None,
    visual_parts: list[dict] | None = None,
    referral: dict | None = None,
) -> None:
    from src.ai.prompts import FORMAT_RETRY_REASONS, format_retry_messages, build_full_prompt
    from src.db.faq_db import search_faq
    from src.services.guard import check_input, check_output, is_rate_limited
    from src.services.llm import (get_llm, get_vision_llm, get_legacy_llm, get_legacy_vision_llm,
                                  response_arguments, response_log_content, tool_enabled_for)
    from src.services.story_media import prepare_images, prepare_shared_media, prepare_story_media
    from src.services.telegram_notify import TelegramNotifier
    from src.services.tour_loader import get_tours_text

    if isinstance(referral, dict) and referral.get("source") == "ADS":
        story = image_urls = shared_sources = image_types = voice_parts = visual_parts = referral = None
        if not text.strip():
            mark_processing("ignored", "ad_without_text")
            return

    # Пауза: если живой менеджер недавно писал в этот чат — бот молчит.
    pre = await get_session(sender_id)
    if _manager_pending.get(sender_id):
        trace_event('processing_skipped', sender_id=sender_id, reason='manager_pending')
        return
    if is_manager_active(pre, settings.manager_takeover_ttl_minutes):
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            if is_manager_active(session, settings.manager_takeover_ttl_minutes):
                logger.info("manager.active.skip_llm", sender_id=sender_id)
                trace_event('processing_skipped', sender_id=sender_id, reason='manager_active')
                return

    is_ad = bool(referral and referral.get("source") == "ADS")
    processing = current_processing.get()
    allow_silent = is_ad or bool(processing and processing.allow_silent)
    typed_text = text if voice_parts is None else "\n".join(part["text"] for part in voice_parts if "text" in part)

    if is_rate_limited(sender_id):
        logger.warning("guard.rate_limited", sender_id=sender_id)
        trace_event('processing_skipped', sender_id=sender_id, reason='input_rate_limited')
        if is_ad:
            await _silent_handoff_body(sender_id, typed_text, "ad_referral")
            return
        await _send_or_queue(
            sender_id,
            "Вы пишете слишком часто. Пожалуйста, подождите минуту 🙏",
        )
        return

    ok, reason = check_input(typed_text or "[Голосовое сообщение]")
    if not ok:
        logger.warning("guard.input_rejected", sender_id=sender_id, reason=reason)
        trace_event('processing_skipped', sender_id=sender_id, reason=reason)
        if is_ad:
            await _silent_handoff_body(sender_id, typed_text, "ad_referral")
            return
        await _send_or_queue(sender_id, _guard_reply(reason))
        return

    media = None
    media_failed = False
    shared_ad_fallback = False
    voice_failed = False
    ad_parts = _ad_visual_parts(referral)
    if voice_parts is not None:
        from src.services.voice_media import transcribe_voice

        async def manager_active():
            return bool(_manager_pending.get(sender_id) or is_manager_active(
                await get_session(sender_id), settings.manager_takeover_ttl_minutes))

        try:
            transcripts = await transcribe_voice([part["audio"] for part in voice_parts if "audio" in part],
                                                 abort=manager_active)
            if await manager_active():
                return
            audio_count = sum("audio" in part for part in voice_parts)
            if len(transcripts) != audio_count or any(not transcript.strip() for transcript in transcripts):
                raise VoiceMediaError("voice_empty")
            iterator = iter(transcripts)
            text = "\n".join(part["text"] if "text" in part else next(iterator) for part in voice_parts)
            ok, reason = check_input(text)
            if not ok:
                if is_ad:
                    await _silent_handoff_body(sender_id, typed_text, "ad_referral")
                    return
                if reason == "too_long":
                    raise VoiceMediaError("voice_text_long")
                await _send_or_queue(sender_id, _guard_reply(reason))
                return
        except VoiceMediaError as exc:
            logger.warning("voice.unavailable", reason=str(exc))
            if is_ad:
                voice_failed = True
                text = typed_text or "[Голосовое не распознано; текст вопроса неизвестен]"
            else:
                await _process_voice_failure(sender_id, typed_text, str(exc))
                return
        if visual_parts and not ad_parts:
            from src.services.story_media import prepare_visual_parts
            try:
                media = await prepare_visual_parts(visual_parts, abort=manager_active)
                if await manager_active():
                    return
                if not media.images:
                    media = None
            except StoryMediaError:
                if is_ad:
                    media_failed = True
                    media = None
                else:
                    await _process_voice_failure(sender_id, typed_text, "voice_visual")
                    return
    use_story = story is not None and settings.story_media_enabled
    use_images = story is None and image_urls is not None and settings.image_media_enabled
    use_shared = story is None and shared_sources is not None and settings.shared_media_enabled
    unavailable_reply = (_AD_UNAVAILABLE if any(part.get("kind") == "ad" for part in ad_parts) else
                         _STORY_UNAVAILABLE if use_story else (_POST_UNAVAILABLE if use_shared else _IMAGE_UNAVAILABLE))
    media_kind = "story" if use_story else ("shared" if use_shared else "image")
    if voice_parts is not None:
        media_kind = "mixed"
    if use_story or use_images or use_shared or ad_parts or (visual_parts and voice_parts is None):
        try:
            if use_images and image_types is not None and (
                    len(image_types) != len(image_urls)
                    or any(kind not in ("image", "story_mention", "video") for kind in image_types)):
                raise StoryMediaError("invalid_image_types")
            if ad_parts:
                from src.services.story_media import prepare_visual_parts
                async def abort_ad_media():
                    return bool(_manager_pending.get(sender_id) or is_manager_active(
                        await get_session(sender_id), settings.manager_takeover_ttl_minutes))
                parts = list(visual_parts or []) if voice_parts is not None else []
                if voice_parts is None:
                    if use_story:
                        parts.append({"kind": "story", "story": story})
                    elif use_shared:
                        parts.append({"kind": "shared", "sources": shared_sources})
                    elif use_images:
                        parts.append({"kind": "images", "urls": image_urls, "types": image_types})
                if use_shared:
                    # Полный входящий пост уже содержит материал для вопроса клиента.
                    try:
                        media = await prepare_shared_media(shared_sources, abort=abort_ad_media)
                        if not media.images:
                            raise StoryMediaError("post_unavailable")
                    except StoryMediaError as exc:
                        if (not any(part.get("kind") == "ad" for part in ad_parts)
                                or str(exc) not in {"post_unavailable", "graph_unavailable", "media_timeout", "download_unavailable"}):
                            raise
                        if await abort_ad_media():
                            return
                        shared_ad_fallback = True
                        parts = []
                        media = await prepare_visual_parts(ad_parts, abort=abort_ad_media)
                    else:
                        ad_parts = []
                else:
                    media = await prepare_visual_parts(parts + ad_parts, abort=abort_ad_media)
                if await abort_ad_media():
                    return
                for image in media.images:
                    if any(image["label"].startswith(f"Источник {index + 1}:")
                           for index in range(len(parts), len(parts + ad_parts))):
                        if media.ad_source == "marketing_variant":
                            image["label"] += " Реклама с вариантами мест показа; показанный клиенту вариант не подтверждён."
                        elif any(part.get("kind") == "ad" for part in ad_parts) and media.ad_source != "clicked_asset":
                            image["label"] += " Точное рекламное объявление из текущего отклика."
                        else:
                            image["label"] += " Рекламный материал из текущего отклика; полнота исходного объявления не гарантируется."
                media_kind = "mixed"
            elif visual_parts and voice_parts is None:
                from src.services.story_media import prepare_visual_parts
                media = await prepare_visual_parts(visual_parts)
                media_kind = "mixed"
            elif use_story:
                media = await prepare_story_media(story.get("id"))
            elif use_shared:
                media = await prepare_shared_media(shared_sources)
            elif image_types is not None:
                media = await prepare_images(image_urls, image_types=image_types)
            else:
                media = await prepare_images(image_urls)
            if not media.images:
                if text == _IMAGE_NO_CAPTION:
                    return
                media, use_images = None, False
            if media:
                logger.info("story.media.prepared" if use_story else "image.media.prepared", story_id=media.story_id,
                            media_type=media.media_type, images=len(media.images))
        except StoryMediaError as exc:
            logger.warning("story.media.unavailable" if use_story else "image.media.unavailable", reason=str(exc))
            media_failed = True
            media = None

    lock = await _get_lock(sender_id)
    async with lock:
        session = await get_session(sender_id)
        if _manager_pending.get(sender_id) or is_manager_active(
            session, settings.manager_takeover_ttl_minutes,
        ):
            return
        history = session.get("history", [])

        tours_text = get_tours_text()
        catalog = catalog_metadata(tours_text)

        faq_context = ""
        try:
            relevant = await search_faq(text)
            if relevant:
                faq_context = "\n\n".join(
                    e["document"] for e in relevant[:3]
                )
        except Exception:
            logger.debug("faq.search_skipped")

        instagram_handle = None if is_ad else await instagram.get_username(sender_id)

        # Считаем ДО перезаписи last_message_at ниже — сброс опирается на время
        # предыдущего сообщения клиента.
        escalation_count = effective_escalation_count(
            session, settings.escalation_reset_hours
        )
        from src.config import MINSK_TZ
        now_minsk = datetime.now(MINSK_TZ)
        current_time = now_minsk.strftime("%H:%M")
        current_date = now_minsk.date()
        is_first = not history
        should_greet, is_first_msg = _should_greet(
            session.get("last_message_at"), is_first,
        )
        prompt_history = [
            {**entry, "content": _strip_markers(entry["content"])}
            if entry.get("role") == "assistant" else {**entry, "content": re.sub(
                r"(?m)^\[(?:Отклик на рекламу|Реклама: содержимое|Исходная публикация/Reels недоступна; обработано "
                r"(?:медиа (?:из отклика на рекламу|рекламного креатива)|точное рекламное объявление))[^\]]*\]\n?",
                "", entry.get("content", "")).strip()}
            for entry in history
        ]
        use_tools = tool_enabled_for(sender_id)
        messages = build_full_prompt(
            tours_text, faq_context,
            trim_history([entry for entry in prompt_history if entry.get("content")], settings.max_history_messages),
            text, escalation_count,
            current_date=current_date,
            current_time=current_time,
            should_greet=should_greet,
            is_first_message=is_first_msg,
            media_images=media.images if media else None,
            media_kind=media_kind,
            media_caption=media.caption if media else "",
            media_image_types=(media.image_types if media and media.image_types is not None else image_types)
                              if use_images or voice_parts is not None else None,
            ad_context=_ad_context(referral) + ("\n[Содержимое рекламы недоступно]" if is_ad and media_failed else "")
                + ("\n[Голосовое не распознано; его содержание неизвестно]" if is_ad and voice_failed else "")
                + ("\n[Файл или товарная карточка недоступны; требуется просмотр менеджером]"
                   if is_ad and referral.get("attachment_requires_manager") else ""),
            use_tools=use_tools,
        )
        if processing and processing.allow_silent:
            from langchain_core.messages import SystemMessage
            messages = [*messages[:-1], SystemMessage(content=(
                "Сообщение восстановлено из переписки Instagram. Контекст источника неполный: "
                "реклама, история или вложение могли не вернуться через API. Не угадывай их содержимое. "
                "Если запрос понятен из текста и переписки, ответь по существу. Если для ответа нужен " +
                ("недоступный источник, вызови prepare_response с пустым reply и кратким manager. " if use_tools else
                 "недоступный источник, верни тот же JSON reply/manager с пустым reply и кратким manager. ") +
                "Это разрешённая молчаливая передача, даже без признака ADS.")), messages[-1]]

        if _manager_pending.get(sender_id):
            return
        response_failure = None
        response_valid = False
        escalation_data = None
        decision = None
        input_phone = _input_phone_from_text(typed_text if voice_parts is not None else text)
        if voice_parts is not None and not input_phone:
            phones = {_normalize_phone(value) for value in re.findall(r"\+\d[\d ()-]{6,20}\d", text)} - {None}
            if len(phones) == 1:
                input_phone = phones.pop()
        response = None
        response_request_id = uuid4().hex
        model_called = not (media_failed and not is_ad)
        if not model_called:
            raw_reply = unavailable_reply
        else:
            attempts = json.loads(processing.job.get('model_attempt_log') or '[]') if processing else []
            try:
                factory = (get_vision_llm if media else get_llm) if use_tools else (get_legacy_vision_llm if media else get_legacy_llm)
                llm = factory()
            except Exception as exc:
                details = dict(attempt=0, stage='configuration', reason='configuration_error', **error_details(exc))
                trace_event('model_error', sender_id=sender_id, request_id=response_request_id, **details)
                await _technical_handoff(sender_id, text, 'configuration_error', response_request_id,
                                         [details], handle=instagram_handle)
                return
            call_messages = messages
            for local_attempt in range(1, 4):
                current_session = await get_session(sender_id)
                if _manager_pending.get(sender_id) or is_manager_active(
                        current_session, settings.manager_takeover_ttl_minutes):
                    return
                attempt = (processing.store.reserve_model_attempt(processing.job, processing.revision, response_request_id)
                           if processing else local_attempt)
                if attempt is None:
                    response_failure = 'model_budget_exhausted'
                    raw_reply = ''
                    break
                timeout = CALL_TIMEOUTS[attempt - 1]
                response = None
                response_fields = _response_metadata(None)
                stage = 'invoke'
                log_model_request(call_messages, sender_id=sender_id, request_id=response_request_id,
                                  phase='primary', attempt=attempt, timeout=timeout,
                                  model=settings.deepseek_vision_model if media else settings.deepseek_model, llm=llm)
                started = asyncio.get_running_loop().time()
                try:
                    # HTTP read timeouts bound inactivity, not total duration.
                    # Cancel the async request before starting the next attempt.
                    response = await asyncio.wait_for(
                        llm.ainvoke(call_messages, **({'timeout': timeout} if attempt == 3 else {})),
                        timeout=timeout)
                    stage = 'decode'
                    raw_reply, response_failure = response_arguments(response) if use_tools else (response.content, None)
                    response_fields = _response_metadata(response)
                    validation_reason = response_failure or _validate_response(raw_reply, allow_silent=allow_silent)[1] or 'valid'
                    if response_fields['finish_reason'] == 'length':
                        validation_reason = 'response_truncated'
                        response_failure = validation_reason
                    log_llm_response(response_log_content(response), request_id=response_request_id, sender_id=sender_id,
                                     attempt=attempt,
                                     model=settings.deepseek_vision_model if media else settings.deepseek_model,
                                     route=('ad_vision' if media else 'ad_text') if is_ad else ('vision' if media else 'text'),
                                     validation_reason=validation_reason, response_fields=response_fields, catalog=catalog)
                    retryable = validation_reason in FORMAT_RETRY_REASONS | {'empty_response', 'response_truncated'}
                    details = dict(attempt=attempt, timeout=timeout, stage='validation', reason=validation_reason)
                except Exception as exc:
                    from src.exceptions import ProviderResponseError
                    response_failure = (exc.reason if isinstance(exc, ProviderResponseError) else
                                        'call_deadline' if isinstance(exc, TimeoutError) else 'provider_error')
                    raw_reply = ''
                    validation_reason = response_failure
                    retryable = stage == 'invoke' and retryable_error(exc)
                    details = dict(attempt=attempt, timeout=timeout, stage=stage, reason=response_failure, **error_details(exc))
                    details['elapsed_ms'] = round((asyncio.get_running_loop().time() - started) * 1000)
                    trace_event('model_error', sender_id=sender_id, request_id=response_request_id,
                                phase='primary', retryable=retryable, **details)
                details['elapsed_ms'] = round((asyncio.get_running_loop().time() - started) * 1000)
                attempts.append(details)
                if processing:
                    processing.store.record_model_attempt(processing.job, details, response_request_id)
                trace_event('model_attempt', sender_id=sender_id, request_id=response_request_id,
                            retryable=retryable, **details)
                current_session = await get_session(sender_id)
                if _manager_pending.get(sender_id) or is_manager_active(
                        current_session, settings.manager_takeover_ttl_minutes):
                    return
                if attempt == 3 or not retryable:
                    break
                if validation_reason in FORMAT_RETRY_REASONS:
                    call_messages = format_retry_messages(messages, validation_reason, use_tools=use_tools)
                event = ('llm.empty_response_retry' if validation_reason == 'empty_response' else
                         'llm.format_response_retry' if validation_reason in FORMAT_RETRY_REASONS else 'llm.call_retry')
                logger.warning(event, sender_id=sender_id, request_id=response_request_id,
                               next_attempt=attempt + 1, retryable=retryable,
                               **{**details, **response_fields, 'attempt': attempt + 1})
            if media and not response_failure:
                usage = _response_metadata(response)
                logger.info('story.vision.completed' if use_story else 'image.vision.completed', story_id=media.story_id,
                            input_tokens=usage.get('input_tokens'), output_tokens=usage.get('output_tokens'))

        if _manager_pending.get(sender_id):
            return

        silent_ad_context = None
        if model_called:
            current_session = await get_session(sender_id)
            if _manager_pending.get(sender_id) or is_manager_active(
                    current_session, settings.manager_takeover_ttl_minutes):
                return
            response_fields = _response_metadata(response)
            if response_fields["finish_reason"] == "length":
                response_failure = "response_truncated"
            result, rejection = (None, response_failure) if response_failure else _validate_response(raw_reply, allow_silent=allow_silent)
            trace_event('model_proposal', sender_id=sender_id, request_id=response_request_id,
                        result=result, rejection=rejection, allow_silent=allow_silent)
            if not result:
                logger.warning('llm.invalid_model_response', sender_id=sender_id,
                               request_id=response_request_id, reason=rejection, **response_fields)
                await _technical_handoff(sender_id, text, rejection, response_request_id, attempts,
                                         handle=instagram_handle)
                return
            else:
                response_valid = True
                if (settings.manager_review_enabled and not input_phone and result['manager']
                        and result['manager']['type'] == 'консультация'
                        and not (referral or {}).get('attachment_requires_manager')):
                    from src.db.manager_tasks import open_tasks
                    decision = HandoffDecision(result)
                    try:
                        tasks = open_tasks(sender_id, store=processing.store if processing else None)
                        decision = await review_manager_candidate(messages, result,
                            tours_text=tours_text, faq_context=faq_context, open_tasks=tasks,
                            sender_id=sender_id, request_id=response_request_id, catalog=catalog,
                            validate=_validate_response, metadata=_response_metadata,
                            allow_silent=allow_silent, vision=bool(media))
                    except Exception:
                        logger.warning('handoff.review.context_unavailable', request_id=response_request_id)
                    if _manager_pending.get(sender_id) or is_manager_active(
                            await get_session(sender_id), settings.manager_takeover_ttl_minutes):
                        return
                    result = decision.response
                raw_reply = result['reply']
                escalation_data = result['manager']
                if allow_silent and not raw_reply.strip():
                    silent_ad_context = escalation_data['context']
                    mark_processing("silent_model_handoff")
            if is_ad and referral.get("attachment_requires_manager"):
                silent_ad_context = silent_ad_context or "Клиент прислал файл или товарную карточку в отклике на рекламу. Требуется просмотр менеджером."
                raw_reply = ""
                mark_processing("human_only")
        elif media_failed:
            mark_processing("technical_retry", "media_unavailable")
        escalation_reason = (escalation_data or {}).get("context")
        escalation_context = (escalation_data or {}).get("context")
        escalation_name = (escalation_data or {}).get("name")
        if escalation_name and _has_contact_phone(escalation_name, set()):
            escalation_name = None
        escalation_phone = input_phone
        escalation_type = (escalation_data or {}).get("type", "консультация")
        phone_only = bool(_normalize_phone(text) or (
            text.startswith("Номер в телефонной карточке: ") and _normalize_phone(
                text.removeprefix("Номер в телефонной карточке: "))))
        if len(text.splitlines()) > 1 and all(
                (number := _normalize_phone(line.removeprefix("Номер в телефонной карточке: ")))
                and number.startswith("+") for line in text.splitlines()):
            phone_only = True
        if input_phone:
            logger.info("escalation.contact.source", sender_id=sender_id, source="current_input")
            escalation_reason = "Клиент оставил номер телефона для связи."
            known_numbers = {number for value in [input_phone,
                *(entry.get("content") for entry in history)] if (number := _normalize_phone(value))}
            current_question = "\n".join(line for line in text.splitlines()
                if not line.startswith("Номер в телефонной карточке: ") and not _normalize_phone(line)).strip()
            current_question = _INLINE_PHONE_RE.sub(
                lambda match: '' if _normalize_phone(match[0]) in known_numbers else match[0],
                current_question).strip()
            if re.fullmatch(
                    r'(?:меня зовут [^,\n]{1,100},\s*)?(?:мой\s+)?'
                    r'(?:номер(?:\s+телефона)?|телефон|контакт)\s*'
                    r'(?:[,.;: ]*(?:позвоните|перезвоните|звоните)(?:\s+мне)?)?[\s,.;:!?]*',
                    current_question, re.IGNORECASE):
                current_question = ''
            # Reuse the existing call's gist; actual phone and current question remain authoritative.
            model_context = escalation_context if response_valid else None
            if current_question or not _valid_manager_context(model_context, known_numbers):
                escalation_context = _contact_escalation_context(current_question, history, known_numbers)
            else:
                escalation_context = " ".join(model_context.split())
            escalation_type = "контакт"
            if escalation_name and _has_contact_phone(escalation_name, known_numbers):
                escalation_name = None
        elif escalation_reason and not _valid_manager_context(escalation_context, set()):
            escalation_context = _contact_escalation_context(
                text, history, set(), intro="Клиент просит консультацию.")

        if silent_ad_context is not None:
            escalation_reason = ("Клиент откликнулся на рекламу. Требуется консультация менеджера." if is_ad else
                                 "Контекст восстановленного сообщения неполный. Требуется консультация менеджера.")
            escalation_context = (silent_ad_context if _valid_manager_context(silent_ad_context, set()) else
                _contact_escalation_context(text, history, set(), intro=escalation_reason))
            escalation_type = "контакт" if input_phone else "консультация"

        clean_reply = _strip_markers(raw_reply) or "Спасибо, ваше сообщение получено."
        clean_reply = check_output(clean_reply)

        contact_sent = False
        contact_failed = False
        handoff_outcome = "none"
        if escalation_reason:
            if escalation_count >= 3 and not (decision and decision.action == 'update'):
                handoff_outcome = "limit"
                logger.info("escalation.limit_reached", sender_id=sender_id, count=escalation_count)
            else:
                try:
                    if is_ad:
                        try:
                            instagram_handle = await instagram.get_username(sender_id)
                        except Exception:
                            logger.warning("instagram.ad.profile_unavailable", sender_id=sender_id)
                        if _manager_pending.get(sender_id) or is_manager_active(
                                await get_session(sender_id), settings.manager_takeover_ttl_minutes):
                            return
                    notifier = TelegramNotifier()
                    receipt = await notifier.notify_manager(
                        sender_id=sender_id,
                        instagram_handle=instagram_handle,
                        context=escalation_context,
                        client_name=escalation_name,
                        client_phone=escalation_phone,
                        tag=escalation_type,
                        **({'decision': decision} if decision is not None else {}),
                    )
                    if getattr(receipt, "deferred", False) is True:
                        handoff_outcome = "deferred"
                    else:
                        escalation_count = (receipt.escalation_count if getattr(receipt, 'managed', False) is True
                                            and type(receipt.escalation_count) is int else escalation_count + 1)
                        handoff_outcome = "sent"
                        contact_sent = bool(input_phone)
                except Exception:
                    handoff_outcome = "failed"
                    contact_failed = bool(input_phone)
                    logger.exception("escalation.notify_failed")

        if _manager_pending.get(sender_id) or is_manager_active(
                await get_session(sender_id), settings.manager_takeover_ttl_minutes):
            trace_event('processing_skipped', sender_id=sender_id, reason='manager_takeover',
                        request_id=response_request_id)
            return

        if phone_only:
            if processing:
                processing.reply_kind = "phone"
            if handoff_outcome == "deferred":
                clean_reply = "Спасибо, ваш номер сохранён."
            elif contact_sent:
                clean_reply = "Спасибо, передал ваш номер менеджерам. Они свяжутся с вами в рабочее время."
            elif contact_failed:
                clean_reply = "Спасибо, ваш номер сохранён. " + _HANDOFF_FAILED_REPLY
            else:
                clean_reply = "Спасибо, ваш номер сохранён. " + _HANDOFF_LIMIT_REPLY
        else:
            clean_reply = _finalize_handoff_reply(clean_reply, handoff_outcome,
                limited=escalation_count >= 3, outside_hours=not 10 <= now_minsk.hour < 18)

        trace_event('application_decision', sender_id=sender_id, request_id=response_request_id,
                    manager_context=escalation_context, manager_type=escalation_type,
                    handoff_outcome=handoff_outcome, escalation_count=escalation_count,
                    silent=silent_ad_context is not None,
                    review_action=decision.action if decision else None)
        trace_event('reply_prepared' if processing else 'final_reply', sender_id=sender_id,
                    request_id=response_request_id, reply=clean_reply,
                    delivery_deferred=bool(processing))

        # Сохраняем user-реплику, НО НЕ assistant — её сохраним только после
        # успешной отправки, чтобы история не врала о недоставленном ответе.
        history_text = re.sub(r"https?://\S+|www\.\S+", "", text).strip() if silent_ad_context is not None else text
        if voice_parts is not None:
            history_text += "\n[Голосовое не распознано]" if voice_failed else "\n[Распознано голосовое сообщение]"
            if visual_parts:
                history_text += "\n[Фото/видео клиента; " + ", ".join(
                    {"story": "ответ на историю", "shared": "публикация/Reels", "images": "вложения"}.get(
                        part.get("kind"), "медиа") for part in visual_parts) + "]"
                if media and "story_mention" in (media.image_types or []):
                    history_text += "\n[Упоминание аккаунта в истории клиента]"
        if shared_ad_fallback:
            if media and media.ad_source == "marketing_variant":
                history_text += "\n[Исходная публикация/Reels недоступна; обработано медиа рекламного креатива, показанный клиенту вариант не подтверждён]"
            elif media and media.ad_source == "clicked_asset":
                history_text += "\n[Исходная публикация/Reels недоступна; обработано медиа из отклика на рекламу, полнота объявления не подтверждена]"
            else:
                history_text += ("\n[Исходная публикация/Reels недоступна; обработано точное рекламное объявление]"
                                 if media else "\n[Исходная публикация/Reels и реклама недоступны]")
        elif media and media.story_id:
            history_text += f"\n[Ответ на историю {media.story_id}, {media.media_type}]"
        elif use_images:
            history_text += f"\n[Изображений: {len(image_urls)}]"
            mentions = [str(index + 1) for index, kind in enumerate(image_types or [])
                        if kind == "story_mention"]
            if mentions:
                history_text += "\n[Story mention: изображения " + ", ".join(mentions) + "]"
            videos = [str(index + 1) for index, kind in enumerate(media.media_types if media and media.media_types else [])
                      if kind == "VIDEO"]
            if videos:
                history_text += "\n[Видео: вложения " + ", ".join(videos) + "; по 10 кадров, без звука]"
        elif use_shared:
            history_text += "\n[Публикация/Reels, медиа обработано]" if media else "\n[Публикация/Reels, медиа недоступно]"
        if _ad_context(referral):
            history_text += "\n" + _ad_context(referral)
            if media_failed:
                history_text += "\n[Реклама: содержимое недоступно]"
            elif media and media.ad_source == "marketing_variant" and not shared_ad_fallback:
                history_text += "\n[Обработано медиа рекламного креатива; показанный клиенту вариант не подтверждён]"
        history.append({"role": "user", "content": history_text})
        session["history"] = history
        session["escalation_count"] = escalation_count
        session["last_message_at"] = datetime.now(timezone.utc).isoformat()
        session.pop("ad_dialog_context", None)
        await save_session(sender_id, session)
        if silent_ad_context is not None:
            return

        # Пытаемся отправить все chunks. В историю попадает только реально
        # доставленное — если chunk N упал, chunks[N:] не пытаемся отправлять
        # (тот же сбой), а сразу ставим в очередь с тем же retry_at. Успешно
        # отправленные до сбоя chunks (sent_chunks) всё равно фиксируем в
        # истории — иначе клиент получил кусок ответа, а бот об этом не помнит.
        chunks = _split_reply(clean_reply)
        sent_chunks: list[str] = []
        for i, chunk in enumerate(chunks):
            if _manager_pending.get(sender_id):
                break
            ok, retry_at = await _send_or_queue(sender_id, chunk)
            if not ok:
                if retry_at is not None or current_processing.get() is not None:
                    for remaining in chunks[i + 1:]:
                        await enqueue_pending(sender_id, remaining, retry_at)
                break
            sent_chunks.append(chunk)

        if sent_chunks:
            history.append({"role": "assistant", "content": " ".join(sent_chunks)})
            session["history"] = history
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)


async def _process_voice_failure(sender_id: str, typed_text: str, code: str) -> None:
    """Immediate human handoff; no model call or invented voice transcript."""
    from src.services.telegram_notify import TelegramNotifier
    mark_processing("technical_retry" if code in {"voice_busy", "voice_worker", "voice_timeout"} else "human_only", code)

    descriptions = {
        "voice_empty": "В голосовом не удалось разобрать речь.",
        "voice_count": "В одном обращении слишком много голосовых.",
        "voice_size": "Голосовое превышает допустимый размер.",
        "voice_duration": "Голосовое превышает допустимую длительность.",
        "voice_text_long": "Распознанный запрос слишком длинный для автоматического ответа.",
        "voice_busy": "Распознавание голосового занято.",
        "voice_visual": "Не удалось прочитать медиа, приложенное к голосовому.",
    }
    lock = await _get_lock(sender_id)
    async with lock:
        session = await get_session(sender_id)
        if _manager_pending.get(sender_id) or is_manager_active(session, settings.manager_takeover_ttl_minutes):
            return
        handle = await instagram.get_username(sender_id)
        if _manager_pending.get(sender_id):
            return
        history = session.get("history", [])
        context = _contact_escalation_context(typed_text, history, set(),
            intro="Клиент прислал голосовое. " + descriptions.get(code, "Не удалось распознать запись."))
        count = effective_escalation_count(session, settings.escalation_reset_hours)
        sent, failed = False, False
        if count < 3:
            try:
                receipt = await TelegramNotifier().notify_manager(sender_id=sender_id, instagram_handle=handle,
                                                        context=context, tag="голосовое")
                if getattr(receipt, "deferred", False) is not True:
                    count += 1
                    sent = True
            except Exception:
                logger.warning("voice.handoff.failed", sender_id=sender_id)
                failed = True
        if _manager_pending.get(sender_id):
            return
        request = "Повторите запись или напишите вопрос текстом, пожалуйста."
        if current_processing.get() and current_processing.get().notifications:
            reply = "Не удалось обработать голосовое. " + request
        elif sent:
            reply = "Не удалось обработать голосовое. Запрос передан менеджеру. " + request
        elif failed:
            reply = ("Не удалось обработать голосовое. " + _HANDOFF_FAILED_REPLY + " " + request +
                     " Менеджеры Наталья и Татьяна: А1 +375 29 356 83 24 / +375 29 152 37 28.")
        else:
            reply = "Не удалось обработать голосовое. " + _HANDOFF_LIMIT_REPLY + " " + request
        history.append({"role": "user", "content": (typed_text + "\n" if typed_text else "") +
                        "[Голосовое сообщение не распознано]"})
        session.update(history=history, escalation_count=count,
                       last_message_at=datetime.now(timezone.utc).isoformat())
        await save_session(sender_id, session)
        if _manager_pending.get(sender_id):
            return
        delivered, _ = await _send_or_queue(sender_id, reply)
        if delivered:
            history.append({"role": "assistant", "content": reply})
            await save_session(sender_id, session)


async def _mark_manager_active(client_id: str, manager_text: str) -> None:
    """Живой менеджер ответил клиенту — ставим/продлеваем паузу бота."""
    try:
        lock = await _get_lock(client_id)
        async with lock:
            from src.services.inbound_recovery import existing_receipt_store
            journal = existing_receipt_store()
            if journal:
                journal.mark_legacy_manager(client_id, manager_text)
                logger.info("manager.takeover", client_id=client_id)
                return
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


async def _process_silent_handoff(sender_id: str, text: str, reason: str) -> None:
    """A proven service event only notifies managers; every outcome remains silent."""
    if reason not in {"story_mention", "ad_referral", "unsupported_type"}:
        return
    processing = _processing_locks.setdefault(sender_id, asyncio.Lock())
    async with processing:
        await _silent_handoff_body(sender_id, text, reason)


async def _silent_handoff_body(sender_id: str, text: str, reason: str) -> None:
    """Caller holds the processing lock; never respond or enqueue on failure."""
    mark_processing("human_only", reason)
    try:
        from src.services.telegram_notify import TelegramNotifier
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            if _manager_pending.get(sender_id) or is_manager_active(session, settings.manager_takeover_ttl_minutes):
                return
            count = effective_escalation_count(session, settings.escalation_reset_hours)
            safe_text = re.sub(r"https?://\S+|www\.\S+", "", text).strip()
            ad = reason == "ad_referral"
            unsupported = reason == "unsupported_type"
            context = ("Клиент ответил на рекламу. Требуется консультация менеджера."
                       if ad else "Клиент прислал неподдерживаемое вложение Instagram. Содержимое недоступно; требуется проверка менеджера."
                       if unsupported else "Клиент упомянул аккаунт компании в своей истории. Содержимое истории бот не распознавал.")
            if safe_text:
                context += " Текст клиента: " + safe_text
            if count < 3:
                try:
                    handle = await instagram.get_username(sender_id)
                except StaleWork:
                    raise
                except Exception as exc:
                    handle = None
                    logger.warning('instagram.silent_handoff.profile_unavailable',
                                   sender_id=sender_id, **error_details(exc))
                if _manager_pending.get(sender_id) or is_manager_active(
                        await get_session(sender_id), settings.manager_takeover_ttl_minutes):
                    return
                try:
                    receipt = await TelegramNotifier().notify_manager(sender_id=sender_id,
                        instagram_handle=handle, context=_brief_context(context, 450),
                        client_phone=_input_phone_from_text(safe_text) if ad else None,
                        tag="консультация" if ad else "Non-text" if unsupported else "Story mention")
                    if getattr(receipt, "deferred", False) is not True:
                        count += 1
                except StaleWork:
                    raise
                except Exception:
                    logger.exception("instagram.silent_handoff.notify_failed", sender_id=sender_id)
            else:
                logger.info("instagram.silent_handoff.limit", sender_id=sender_id, count=count)
            history = session.get("history", [])
            history.append({"role": "user", "content": (safe_text + "\n[Отклик на рекламу; передача менеджеру без ответа]").strip()
                           if ad else (safe_text + "\n[Неподдерживаемое вложение Instagram]").strip()
                           if unsupported else "[Упоминание аккаунта в истории; содержимое не распознавалось]"})
            session.update(history=history, escalation_count=count,
                           last_message_at=datetime.now(timezone.utc).isoformat())
            if ad:
                session.pop("ad_dialog_context", None)
            await save_session(sender_id, session)
    except StaleWork:
        raise
    except Exception:
        logger.exception("instagram.silent_handoff.failed", sender_id=sender_id)


async def _process_non_text_safely(sender_id: str, text: str, metadata: dict) -> None:
    """Обработка non-text сообщения (вложение, shared post, story reply).

    Не вызывает LLM. Передаёт информацию менеджеру через Telegram
    и отвечает клиенту после общего окна сбора в webhook.
    """
    mark_processing("human_only")
    processing = current_processing.get()
    if processing:
        processing.history_prefix = "[Служебное сообщение о вложении из прошлого — не повторять] "
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
            if (_manager_pending.get(sender_id)
                    or is_manager_active(session, settings.manager_takeover_ttl_minutes)):
                return
            instagram_handle = await instagram.get_username(sender_id)
            if _manager_pending.get(sender_id):
                return
            escalation_count = effective_escalation_count(
                session, settings.escalation_reset_hours
            )
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
                    receipt = await notifier.notify_manager(
                        sender_id=sender_id,
                        instagram_handle=instagram_handle,
                        context=context_msg,
                        tag="Non-text",
                    )
                    if getattr(receipt, "deferred", False) is not True:
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
                        "Я не могу прочитать это вложение. " + _HANDOFF_FAILED_REPLY + " "
                        "Напишите, пожалуйста, ваш вопрос текстом."
                    )
                else:
                    client_reply = (
                        "Спасибо! Я не вижу содержимое вложения, "
                        "поэтому передал ваш вопрос менеджеру.\n"
                        "Он посмотрит и поможет 🙌"
                    )
                    if getattr(receipt, "deferred", False) is True:
                        client_reply = "Я не вижу содержимое вложения. Напишите, пожалуйста, ваш вопрос текстом."
            else:
                logger.info(
                    "instagram.non_text.escalation_skipped_limit",
                    sender_id=sender_id,
                    count=escalation_count,
                )
                client_reply = (
                    _HANDOFF_LIMIT_REPLY
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

        # 4. Ответить клиенту: ожидание уже выполнено до эскалации.
        if (_manager_pending.get(sender_id) or is_manager_active(
                await get_session(sender_id), settings.manager_takeover_ttl_minutes)):
            return
        ok, _ = await _send_or_queue(sender_id, client_reply)
        if not ok:
            return

        # Отправлено успешно — добавляем реплику ассистента в историю.
        # Копию помечаем служебным тегом: иначе LLM на следующий день видит
        # фразу про вложение «своей» репликой и повторяет её на обычный текст
        # (прод-кейс 2026-09-26). Клиенту тег не уходит — ему уже отправлен
        # чистый client_reply выше.
        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            history = session.get("history", [])
            history.append({
                "role": "assistant",
                "content": (
                    "[Служебное сообщение о вложении из прошлого — "
                    "не повторять] " + client_reply
                ),
            })
            session["history"] = history
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)
    except StaleWork:
        raise
    except Exception as exc:
        await _processing_failure(sender_id, text, 'non_text_processing_failed', exc)


async def _process_shared_post_safely(sender_id: str) -> None:
    """Уточнить запрос без подписи после общего окна сбора webhook."""
    mark_processing("human_only")
    try:
        pre = await get_session(sender_id)
        if is_manager_active(pre, settings.manager_takeover_ttl_minutes):
            lock = await _get_lock(sender_id)
            async with lock:
                session = await get_session(sender_id)
                if is_manager_active(session, settings.manager_takeover_ttl_minutes):
                    logger.info(
                        "manager.active.skip_shared_post",
                        sender_id=sender_id,
                    )
                    return

        from src.services.telegram_notify import TelegramNotifier

        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            instagram_handle = await instagram.get_username(sender_id)
            escalation_count = effective_escalation_count(
                session, settings.escalation_reset_hours
            )

            if escalation_count < 3:
                try:
                    notifier = TelegramNotifier()
                    receipt = await notifier.notify_manager(
                        sender_id=sender_id,
                        instagram_handle=instagram_handle,
                        context=(
                            "Клиент поделился публикацией Instagram без подписи. "
                            "Бот попросил уточнить, что именно его заинтересовало."
                        ),
                        tag="Shared post",
                    )
                    if getattr(receipt, "deferred", False) is not True:
                        escalation_count += 1
                    logger.info(
                        "instagram.shared_post.escalated",
                        sender_id=sender_id,
                    )
                except Exception:
                    logger.exception(
                        "instagram.shared_post.notify_failed",
                        sender_id=sender_id,
                    )
            else:
                logger.info(
                    "instagram.shared_post.escalation_skipped_limit",
                    sender_id=sender_id,
                    count=escalation_count,
                )

            session["escalation_count"] = escalation_count
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)

        ok, _ = await _send_or_queue(sender_id, _SHARED_POST_CLARIFICATION)
        if not ok:
            return

        lock = await _get_lock(sender_id)
        async with lock:
            session = await get_session(sender_id)
            history = session.get("history", [])
            history.append(
                {"role": "assistant", "content": _SHARED_POST_CLARIFICATION}
            )
            session["history"] = history
            session["last_message_at"] = datetime.now(timezone.utc).isoformat()
            await save_session(sender_id, session)

        logger.info(
            "instagram.shared_post.clarification_sent",
            sender_id=sender_id,
        )
    except StaleWork:
        raise
    except Exception as exc:
        await _processing_failure(sender_id, '', 'shared_processing_failed', exc)


async def _process_safely(
    sender_id: str, text: str, story: dict | None = None,
    image_urls: list[object] | None = None,
    shared_sources: list[dict] | None = None,
    image_types: list[str] | None = None,
    voice_parts: list[dict] | None = None,
    visual_parts: list[dict] | None = None,
    referral: dict | None = None,
) -> None:
    """Фоновая обработка сообщения.

    Запускается через asyncio.create_task после немедленного ответа 200 Meta.
    Логирует свои ошибки, т.к. request-контекст уже закрыт.
    """
    if isinstance(referral, dict) and referral.get("source") == "ADS":
        story = image_urls = shared_sources = image_types = voice_parts = visual_parts = referral = None
        if not text.strip():
            mark_processing("ignored", "ad_without_text")
            return
    try:
        if referral:
            await process_with_ai(sender_id, text, story, image_urls=image_urls, shared_sources=shared_sources,
                                  image_types=image_types, voice_parts=voice_parts, visual_parts=visual_parts,
                                  referral=referral)
        elif voice_parts is not None:
            await process_with_ai(sender_id, text, voice_parts=voice_parts, visual_parts=visual_parts)
        elif visual_parts:
            await process_with_ai(sender_id, text, visual_parts=visual_parts)
        elif shared_sources is not None:
            await process_with_ai(sender_id, text, story, shared_sources=shared_sources)
        elif image_urls is not None and image_types is not None:
            await process_with_ai(sender_id, text, story, image_urls=image_urls, image_types=image_types)
        elif image_urls is not None:
            await process_with_ai(sender_id, text, story, image_urls=image_urls)
        elif story is None:
            await process_with_ai(sender_id, text)
        else:
            await process_with_ai(sender_id, text, story)
    except StaleWork:
        raise
    except Exception as exc:
        await _processing_failure(sender_id, text, 'processing_exception', exc)


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


async def _notify_tour_sync(text: str) -> None:
    """Уведомление о синхронизации туров менеджерам (если включено)."""
    if not settings.tour_sync_notify:
        return
    try:
        from src.services.telegram_notify import TelegramNotifier

        await TelegramNotifier().notify_manager(
            sender_id="tour_sync", context=text, tag="Tour sync"
        )
    except Exception:
        logger.exception("tour_sync.notify_failed")


async def _apply_tour_sync_result(snapshot: dict, info: dict) -> None:
    """Опубликовать результат тика: память + снапшот + лог + Telegram."""
    from src.services import tour_sync as ts
    from src.services.tour_loader import publish_tours_text, save_snapshot

    publish_tours_text(snapshot["text"])
    try:
        save_snapshot(settings.tour_sync_snapshot_path, snapshot)
    except Exception:
        logger.exception("tour_sync.snapshot_save_failed")
    app.state.tours_text = snapshot["text"]

    diff, skipped = info.get("diff", {}), info.get("skipped", [])
    if diff.get("added") or diff.get("removed") or diff.get("changed") or skipped:
        await _notify_tour_sync(ts.format_diff_message(diff, skipped))


def _initial_tour_sync() -> None:
    """Первая попытка sync при старте: Drive → снапшот → остаётся DOCX.

    Вызывается из потока `_load_tours` после локальной загрузки, так что
    seed для подхвата ссылок на бронирование уже в памяти. Без сети и без
    снапшота просто остаётся загруженное из DOCX.
    """
    from src.services import tour_sync as ts
    from src.services.tour_loader import (
        get_tours_text,
        load_snapshot,
        publish_tours_text,
        save_snapshot,
    )

    if (
        not settings.tour_sync_enabled
        or not settings.tour_sync_folder_id
        or not (settings.google_drive_credentials_file or settings.google_drive_api_key)
    ):
        logger.info("tour_sync.disabled")
        return

    prev = load_snapshot(settings.tour_sync_snapshot_path)
    try:
        snapshot, info = ts.sync_now(
            httpx.get,
            settings.tour_sync_folder_id,
            {
                "credentials_file": settings.google_drive_credentials_file,
                "api_key": settings.google_drive_api_key,
            },
            prev,
            get_tours_text(),
            ts.parse_aliases(settings.tour_sync_name_aliases),
            settings.tour_sync_min_tours,
            settings.tour_sync_max_drop_ratio,
        )
    except Exception as exc:
        # OAuth refresh can fail outside httpx (for example, before DNS is up).
        logger.warning("tour_sync.initial_failed", error=type(exc).__name__)
        snapshot, info = None, {"status": "error"}
    if snapshot is None:
        logger.warning("tour_sync.initial_skipped", reason=info.get("reason", info.get("status")))
        if prev:
            publish_tours_text(prev["text"])
            app.state.tours_text = prev["text"]
            logger.info("tour_sync.snapshot_fallback", chars=len(prev["text"]))
        return
    publish_tours_text(snapshot["text"])
    try:
        save_snapshot(settings.tour_sync_snapshot_path, snapshot)
    except Exception:
        logger.exception("tour_sync.snapshot_save_failed")
    app.state.tours_text = snapshot["text"]
    if info.get("status") == "ok":
        diff, skipped = info.get("diff", {}), info.get("skipped", [])
        if diff.get("added") or diff.get("removed") or diff.get("changed") or skipped:
            asyncio.run(_notify_tour_sync(ts.format_diff_message(diff, skipped)))


async def _tour_sync_worker():
    """Фоновый воркер синхронизации туров из Google Drive.

    Запускается в lifespan как asyncio.create_task. Раз в
    tour_sync_interval_seconds опрашивает папку; публикует в память только
    изменившуюся и провалидированную сборку. Любая ошибка — лог, цикл живёт.
    """
    from src.services import tour_sync as ts
    from src.services.tour_loader import get_tours_text, load_snapshot

    # Ждём первичную загрузку, иначе гонка с `_load_tours` за память/снапшот.
    await asyncio.to_thread(_tours_initial_loaded.wait, 180)

    snapshot = load_snapshot(settings.tour_sync_snapshot_path)
    fail_streak = 0
    last_alert: str | None = None
    disabled_logged = False

    while True:
        await asyncio.sleep(settings.tour_sync_interval_seconds)
        if not settings.tour_sync_enabled:
            continue
        try:
            # Сетевые вызовы — в потоке, чтобы не стопать event loop.
            # Неуспешный тик возвращает None вместо снапшота — им нельзя
            # затирать последний хороший (прод-кейс 2026-10-04: один сбойный
            # тик обнулил состояние, следующий потерял брони и выкинул 2 тура).
            new_snapshot, info = await asyncio.to_thread(
                ts.sync_now,
                httpx.get,
                settings.tour_sync_folder_id,
                {
                    "credentials_file": settings.google_drive_credentials_file,
                    "api_key": settings.google_drive_api_key,
                },
                snapshot,
                get_tours_text(),
                ts.parse_aliases(settings.tour_sync_name_aliases),
                settings.tour_sync_min_tours,
                settings.tour_sync_max_drop_ratio,
            )
            snapshot = ts.keep_snapshot(snapshot, new_snapshot)
        except Exception:
            logger.exception("tour_sync.tick_failed")
            continue

        status = info.get("status")
        if status == "disabled":
            if not disabled_logged:
                logger.info("tour_sync.disabled")
                disabled_logged = True
            continue
        disabled_logged = False

        if status == "unchanged":
            fail_streak = 0
            last_alert = None
            if snapshot and get_tours_text() != snapshot["text"]:
                from src.services.tour_loader import publish_tours_text

                publish_tours_text(snapshot["text"])
                app.state.tours_text = snapshot["text"]
            continue

        if status == "ok":
            fail_streak = 0
            last_alert = None
            try:
                await _apply_tour_sync_result(snapshot, info)
            except Exception:
                logger.exception("tour_sync.apply_failed")
            continue

        if status == "auth_error":
            key = "auth:" + str(info.get("reason", ""))
            if key != last_alert:
                last_alert = key
                await _notify_tour_sync(
                    "❌ Синхронизация туров: " + str(info.get("reason", "ошибка доступа"))
                    + ". Проверьте ключ и доступ к папке. Бот отвечает по последней версии."
                )
            continue

        if status == "invalid":
            key = "invalid:" + str(info.get("reason", ""))
            if key != last_alert:
                last_alert = key
                await _notify_tour_sync(
                    "⚠️ Синхронизация туров отклонена: " + str(info.get("reason", ""))
                    + ". Осталась последняя рабочая версия."
                )
            continue

        # status == "error": транспортный сбой, алерт после N подряд.
        fail_streak += 1
        if fail_streak == settings.tour_sync_alert_after_failures:
            await _notify_tour_sync(
                f"⚠️ Синхронизация туров недоступна ({fail_streak} подряд): "
                f"{info.get('reason', '')}. Работаем по последней версии."
            )


async def _deliver_legacy_manager_tick(store=None):
    """Retry only proven-unsent Telegram intents; share the business client lock."""
    from src.db.inbound import InboundStore, StaleWork
    from src.db.manager_tasks import due_legacy_operations
    from src.services.telegram_notify import TelegramNotifier
    from src.db import sessions

    if store is None and not sessions.DB_PATH.is_file():
        return
    store = store or InboundStore()
    operations = due_legacy_operations(store)
    for client in dict.fromkeys(operation['client_id'] for operation in operations):
        lock = await _get_lock(client)
        async with lock:
            if _manager_pending.get(client):
                continue
            own_operations = [store.get_delivery(operation['id']) for operation in operations
                              if operation['client_id'] == client]
            try:
                await TelegramNotifier().deliver_task_operations(client, own_operations, store=store)
            except StaleWork:
                logger.info('telegram.task.superseded', sender_id=client)
            except Exception:
                logger.warning('telegram.task.retry_pending', sender_id=client)


async def _manager_notifications_worker():
    while True:
        try:
            await _deliver_legacy_manager_tick()
        except Exception:
            logger.warning('telegram.task.worker_failed')
        await asyncio.sleep(30)


async def _pending_messages_worker():
    """Фоновый воркер, досылающий сообщения из очереди pending_messages.

    Запускается в lifespan как asyncio.create_task. Опрашивает очередь
    каждые pending_worker_interval_seconds, отправляет due-сообщения
    (с per-user блокировкой, чтобы не было гонки с обычной обработкой).
    """
    while True:
        await asyncio.sleep(settings.pending_worker_interval_seconds)
        if settings.inbound_recovery_enabled:
            _get_recovery().store.import_legacy_pending()
            _get_recovery().wakeup.set()
        due = await get_due_pending(datetime.now(timezone.utc).isoformat())
        for row in due:
            if settings.inbound_recovery_enabled and settings.recovery_allows(row["recipient_id"]):
                continue
            lock = await _get_lock(row["recipient_id"])
            async with lock:
                try:
                    if not row.get("recovery_delivery_id"):
                        from src.services.inbound_recovery import existing_receipt_store
                        journal = existing_receipt_store()
                        if journal and (not settings.inbound_recovery_enabled or settings.recovery_allows(row["recipient_id"])):
                            journal.import_legacy_pending()
                            row["recovery_delivery_id"] = journal.pending_delivery_id(row["id"])
                    if row.get("recovery_delivery_id"):
                        recovery = _get_recovery()
                        delivery = recovery.store.get_delivery(row["recovery_delivery_id"])
                        if delivery:
                            job = recovery.store.get_job(delivery["job_id"])
                            await recovery.send_part(job, delivery, None, legacy_pending=True)
                            recovery.store.complete_delivery(job, settings.inbound_semantic_recheck_seconds)
                        continue
                    if _manager_pending.get(row["recipient_id"]):
                        continue
                    session = await get_session(row["recipient_id"])
                    if is_manager_active(session, settings.manager_takeover_ttl_minutes):
                        await delete_pending(row["id"])
                        logger.info("pending.cancelled_manager", id=row["id"])
                        continue
                    with trace_scope(row['recipient_id'], pending_id=row['id']):
                        trace_event('final_reply', sender_id=row['recipient_id'], reply=row['text'],
                                    pending_id=row['id'])
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


def _remember_story_reaction(ev: dict) -> None:
    """Silent, bounded exact-ID hint; never retain a media URL or reaction text."""
    now = monotonic()
    for sender, (expires, _) in list(_story_reactions.items()):
        if expires > now:
            break  # insertion order is expiration order
        _story_reactions.pop(sender)
    sender_id = ev["sender_id"]
    _story_reactions.pop(sender_id, None)
    story_id = ev.get("story", {}).get("id")
    if settings.story_media_enabled and story_id:
        _story_reactions[sender_id] = (now + _STORY_REACTION_TTL_SECONDS, {"id": story_id})
        while len(_story_reactions) > _STORY_REACTIONS_MAX:
            _story_reactions.pop(next(iter(_story_reactions)))
        logger.info("instagram.story_context.saved", sender_id=sender_id, story_id=story_id)


_INLINE_PHONE_RE = re.compile(
    r'(?<![\w+])(?:\+[0-9]|375|8[ (\u00a0-]*0)[0-9 ()\u00a0-]{5,28}[0-9](?!\w)')


def _input_phone_from_text(text: str) -> str | None:
    phone = _normalize_phone(text)
    if phone:
        return phone
    for line in reversed(text.splitlines()):
        candidate = _normalize_phone(line.removeprefix("Номер в телефонной карточке: "))
        # Отдельная строка даты/бюджета в пакете не является контактом.
        if candidate and (line.startswith("Номер в телефонной карточке: ") or candidate.startswith("+")):
            return candidate
    # Explicit international/BY numbers inside the current sentence; never a
    # historical/model contact or an arbitrary date/budget. Ambiguity stays empty.
    candidates = {_normalize_phone(value) for value in _INLINE_PHONE_RE.findall(text)}
    phones = {value for value in candidates if value and value.startswith('+')}
    return next(iter(phones)) if len(phones) == 1 else None


def _is_plain_story_followup(ev: dict) -> bool:
    return (ev["kind"] == "user" and bool(ev.get("text", "").strip())
            and not ev.get("_ad_text_only")
            and not any(key in ev for key in ("story", "images", "shared_sources", "non_text", "referral", "phone_card", "voice_parts"))
            and not InstagramChannel._is_reaction_only(ev["text"])
            and not _input_phone_from_text(ev["text"]))


@app.post("/webhook/instagram")
async def receive_instagram_message(request: Request):
    global _last_webhook_at

    raw_body = await request.body()
    # Фиксируем факт обращения ДО проверки подписи — так даже невалидные
    # запросы отразятся в last_seen (полезно при диагностике Live/Dev mode).
    _last_webhook_at = datetime.now(timezone.utc)

    sig = request.headers.get("X-Hub-Signature-256")
    if not instagram.verify_signature(raw_body, sig):
        logger.warning("instagram.webhook.invalid_signature", **webhook_rejection_fields(
            raw_body, sig, settings.instagram_app_secret, request.headers,
            request.client.host if request.client else None))
        return Response(status_code=403, content="Invalid signature")

    try:
        payload = await request.json()
    except (ValueError, UnicodeDecodeError):
        logger.warning("instagram.webhook.invalid_json")
        return Response(status_code=400, content="Invalid JSON")
    if settings.inbound_recovery_enabled:
        recovery = _get_recovery()
        recovery_payload, legacy_payload = _split_recovery_payload(payload)
        try:
            events = await instagram.receive_message(recovery_payload, merge=False, recovery_store=recovery.store)
            recovery.accept(events)
        except Exception:
            logger.error("inbound.webhook.persist_failed")
            return Response(status_code=503, content="Storage unavailable")
        logger.info("instagram.webhook.received", events=len(events))
        payload = legacy_payload
    events = await instagram.receive_message(payload, processed_mids=_processed_mids, merge=False)
    logger.info("instagram.webhook.received", events=len(events))
    # Enables the pre-activation API MID check without logging the message body,
    # full identifiers or switching recovery on merely to observe one webhook.
    for event in events:
        if event.get("mid"):
            logger.info("instagram.inbound.observed", mid_hash=hashlib.sha256(event["mid"].encode()).hexdigest()[:16],
                        kind=event.get("kind"))

    # Запускаем обработку в фоне и отвечаем Meta 200 мгновенно.
    for ev in events:
        log_inbound(ev, source='webhook')
        mid = ev.get("mid", "")
        mids = [mid, *ev.get("related_mids", [])]
        mids = list(dict.fromkeys(message_id for message_id in mids if message_id))
        if mids:
            duplicate_mid = next(
                (message_id for message_id in mids if message_id in _processed_mids),
                None,
            )
            if duplicate_mid:
                logger.info("instagram.webhook.dedup_skipped", mid=duplicate_mid)
                log_inbound(ev, source='webhook', status='duplicate')
                continue
            for message_id in mids:
                _processed_mids.add(message_id)
            while len(_processed_mids) > _PROCESSED_MIDS_MAX:
                _processed_mids.pop_oldest()
        else:
            logger.warning("instagram.message.no_mid", kind=ev.get("kind"))
            continue

        if ev["kind"] == "story_context":
            log_inbound(ev, source='webhook', status='context_only')
            _remember_story_reaction(ev)
            continue
        if ev["kind"] == "ignored":
            continue
        if ev["kind"] == "manager":
            client_id = ev["client_id"]
            _story_reactions.pop(client_id, None)
            _manager_pending[client_id] = _manager_pending.get(client_id, 0) + 1
            _inbound_batches.pop(client_id, None)
            waiting = _inbound_tasks.pop(client_id, None)
            if waiting is not None:
                waiting.cancel()
            task = asyncio.create_task(
                _mark_manager_active(ev["client_id"], ev.get("text", ""))
            )
            def clear_manager_pending(completed: asyncio.Task, client_id: str = client_id) -> None:
                count = _manager_pending.get(client_id, 0) - 1
                if count > 0:
                    _manager_pending[client_id] = count
                else:
                    _manager_pending.pop(client_id, None)
            task.add_done_callback(clear_manager_pending)
        else:
            sender_id = ev["sender_id"]
            recent = _story_reactions.pop(sender_id, None)
            if (recent and recent[0] > monotonic() and settings.story_media_enabled
                    and _is_plain_story_followup(ev)):
                # Snapshot at receipt: a later reaction cannot replace this question's story.
                ev["_reaction_story"] = recent[1]
            if sender_id in _inbound_batches:
                _inbound_batches[sender_id].append(ev)
                # Only the collector is registered here; running AI has already
                # popped its batch/task. Start five quiet seconds from this MID.
                waiting = _inbound_tasks.get(sender_id)
                if waiting is not None:
                    waiting.cancel()
            else:
                _inbound_batches[sender_id] = [ev]
            task = asyncio.create_task(_process_inbound_batch(sender_id))
            _inbound_tasks[sender_id] = task
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return Response(status_code=200, content="")


async def _wait_inbound_window() -> None:
    await asyncio.sleep(_INBOUND_WAIT_SECONDS)


_recovery: RecoveryService | None = None


def _split_recovery_payload(payload):
    """Partition before parsing, including recipient identity of outgoing echoes."""
    recovery, legacy = {**payload, "entry": []}, {**payload, "entry": []}
    for entry in payload.get("entry", []):
        selected, remaining = [], []
        for messaging in entry.get("messaging", []):
            message = messaging.get("message") or {}
            participant = messaging.get("recipient" if message.get("is_echo") else "sender") or {}
            (selected if settings.recovery_allows(participant.get("id")) else remaining).append(messaging)
        if selected:
            recovery["entry"].append({**entry, "messaging": selected})
        if remaining:
            legacy["entry"].append({**entry, "messaging": remaining})
    return recovery, legacy


def _merge_recovery_events(events):
    """Reuse the quiet-window merge and exact story hint affinity."""
    events = [text_only_ad_event(event) for event in events]
    if any(not _is_plain_story_followup(event) for event in events if not event.get("_empty_generic")):
        for event in events:
            event.pop("_reaction_story", None)
    else:
        for event in events:
            hint = _get_recovery().store.story_hint(event["sender_id"], event.get("_event_time") or datetime.now(timezone.utc).timestamp(), mid=event.get("mid"))
            if hint and settings.story_media_enabled:
                event["_reaction_story"] = hint
                logger.info("instagram.story_context.attached", sender_id=event["sender_id"],
                            story_id=hint["id"], source="recovery_merge",
                            mid_hash=hashlib.sha256(event.get("mid", "").encode()).hexdigest()[:16])
    merged = instagram.merge_events(events)
    for event in merged:
        hint = event.pop("_reaction_story", None)
        if hint and settings.story_media_enabled and _is_plain_story_followup(event):
            event["story"] = hint
            event["_story_hint"] = True
    return merged


def _finalize_recovery_reply(result, outcome):
    reply = result.get("reply", "")
    if not reply:
        return ""
    if result.get("reply_kind") == "phone" and result.get("has_notification"):
        if outcome == "sent":
            return "Спасибо, передал ваш номер менеджерам. Они свяжутся с вами в рабочее время."
        return "Спасибо, ваш номер сохранён. " + _HANDOFF_FAILED_REPLY
    if result.get("has_notification"):
        from src.config import MINSK_TZ
        return _finalize_handoff_reply(reply, outcome, outside_hours=not 10 <= datetime.now(MINSK_TZ).hour < 18)
    if result.get("notification_limited"):
        return _finalize_handoff_reply(reply, "limit")
    return reply


def _get_recovery():
    global _recovery
    if _recovery is None:
        _recovery = RecoveryService(instagram, _dispatch_user_event, _merge_recovery_events,
            _finalize_recovery_reply, _split_reply, lambda client: bool(_manager_pending.get(client)))
    return _recovery


@app.get("/api/admin/inbound-recovery")
async def inbound_recovery_status(x_admin_token: str | None = Header(default=None, alias="X-Admin-Token")):
    _require_admin_token(x_admin_token)
    if not settings.inbound_recovery_enabled:
        from src.services.inbound_recovery import existing_receipt_store
        store = existing_receipt_store()
        return {"enabled": False, **(store.stats() if store else {})}
    recovery = _get_recovery()
    return {"enabled": True, "scope": settings.inbound_recovery_scope,
            "allowlist_count": len(settings.recovery_clients()), **recovery.store.stats(),
            "complete_scan_at": recovery.store.get_sync("complete_scan:"+recovery.account)}


async def _process_inbound_batch(sender_id: str) -> None:
    current = asyncio.current_task()
    try:
        await _wait_inbound_window()
        # Следующее сообщение открывает новое окно даже во время медленного AI.
        events = _inbound_batches.pop(sender_id, [])
        _inbound_tasks.pop(sender_id, None)
        if any(not _is_plain_story_followup(event) for event in events
               if not event.get("_empty_generic")):
            # Explicit media/phone/referral contexts take precedence over a silent hint.
            for event in events:
                event.pop("_reaction_story", None)
        merged = instagram.merge_events(events)
        for event in merged:
            story = event.pop("_reaction_story", None)
            if story and settings.story_media_enabled and _is_plain_story_followup(event):
                event["story"] = story
                logger.info("instagram.story_context.attached", sender_id=sender_id, story_id=story["id"])
        logger.info("instagram.batch.ready", sender_id=sender_id,
                    received=len(events), dispatched=len(merged))
        lock = _inbound_locks.setdefault(sender_id, asyncio.Lock())
        async with lock:
            for event in merged:
                if _manager_pending.get(sender_id):
                    logger.info("manager.pending.skip_batch", sender_id=sender_id)
                    return
                legacy_token = legacy_processing.set(event)
                try:
                    await _dispatch_user_event(event)
                finally:
                    legacy_processing.reset(legacy_token)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("instagram.batch.failed", sender_id=sender_id)
    finally:
        if _inbound_tasks.get(sender_id) is current:
            _inbound_tasks.pop(sender_id, None)
            _inbound_batches.pop(sender_id, None)


@traced_flow('inbound')
async def _dispatch_user_event(ev: dict) -> None:
    ev = text_only_ad_event(ev)
    if ev.get("kind") in ("ignored", "story_context", "own_echo"):
        trace_event('processing_skipped', sender_id=ev.get('sender_id'), reason=ev.get('kind'))
        if ev.get("_ad_text_only"):
            mark_processing("ignored", "ad_without_text")
        return
    sender_id = ev["sender_id"]
    if ev.get("kind") == "user_silent_handoff" and ev.get("silent_reason") != "ad_referral":
        await _process_silent_handoff(sender_id, ev.get("text", ""), ev.get("silent_reason", ""))
    elif (ev.get("referral") or {}).get("source") == "ADS":
        ad_text = ev.get("text", "").strip() or "[Отклик на рекламу без вопроса]"
        referral = ev["referral"]
        if any(kind in ("file", "product", "ig_product") for kind in ev.get("non_text", {}).get("types", [])):
            referral = {**referral, "attachment_requires_manager": True}
        await _process_safely(sender_id, ad_text,
                                  ev.get("story"), image_urls=ev.get("images"), image_types=ev.get("image_types"),
                                  shared_sources=ev.get("shared_sources"), voice_parts=ev.get("voice_parts"),
                                  visual_parts=ev.get("visual_parts"), referral=referral)
    elif any(kind in ("file", "product", "ig_product") for kind in ev.get("non_text", {}).get("types", [])):
        await _process_non_text_safely(sender_id, ev.get("text", ""), ev.get("non_text", {}))
    elif ev.get("referral") and (ev["kind"] == "user" or any(key in ev for key in ("story", "images", "shared_sources", "voice_parts"))):
        await _process_safely(sender_id, ev.get("text", "").strip() or "[Отклик на рекламу без вопроса]",
                              ev.get("story"), image_urls=ev.get("images"), image_types=ev.get("image_types"),
                              shared_sources=ev.get("shared_sources"), voice_parts=ev.get("voice_parts"),
                              visual_parts=ev.get("visual_parts"), referral=ev["referral"])
    elif "voice_parts" in ev and settings.voice_media_enabled:
        await _process_safely(sender_id, ev.get("text", "") or "[Голосовое сообщение]",
                              voice_parts=ev["voice_parts"], visual_parts=ev.get("visual_parts", []))
    elif ev.get("visual_parts"):
        await _process_safely(sender_id, ev.get("text") or _POST_NO_QUESTION, visual_parts=ev["visual_parts"])
    elif "story" in ev and ev.get("text") and settings.story_media_enabled:
        await _process_safely(sender_id, ev["text"], ev["story"])
    elif "images" in ev and settings.image_media_enabled:
        text = ev.get("text", "").strip() or _IMAGE_NO_CAPTION
        if "image_types" in ev:
            await _process_safely(sender_id, text, image_urls=ev["images"], image_types=ev["image_types"])
        else:
            await _process_safely(sender_id, text, image_urls=ev["images"])
    elif "shared_sources" in ev and settings.shared_media_enabled:
        await _process_safely(sender_id, ev.get("text", "").strip() or _POST_NO_QUESTION,
                              shared_sources=ev["shared_sources"])
    elif ev["kind"] == "user_shared_post":
        logger.info("instagram.shared_post.processing", sender_id=sender_id)
        await _process_shared_post_safely(sender_id)
    elif ev["kind"] == "user_non_text":
        nt_text = ev.get("text", "")
        if nt_text:
            summary = ev.get("non_text", {}).get("summary", "")
            await _process_safely(sender_id, f"{nt_text}\n\n[Клиент также отправил: {summary}]")
        else:
            await _process_non_text_safely(sender_id, "", ev.get("non_text", {}))
    else:
        logger.info("instagram.message.processing", sender_id=sender_id)
        await _process_safely(sender_id, ev["text"])
