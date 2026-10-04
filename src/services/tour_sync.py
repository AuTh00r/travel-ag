"""Синхронизация базы туров из папки Google Drive (in-process).

Как это работает:
- Воркер в `lifespan` (`src/main.py`) раз в `tour_sync_interval_seconds`
  опрашивает Drive API (`files.list` по ID папки) и скачивает экспортом
  только документы с изменившимся `modifiedTime`.
- Каждый документ собирается в секцию тура той же обработкой, что и
  `tour_loader._extract_tour_section`: нормализация виз, фильтр прошедших
  и распроданных дат, лимит ближайших дат.
- Идентичность тура между тиками — по ID документа (названия могут меняться).
- Ссылки на бронирование в Google-документах обычно нет (проверено), поэтому:
  приоритет — строка «Ссылка на бронирование» внутри документа, затем
  перенос из прошлого состояния по ID, затем подхват из текущей базы по
  названию (bootstrap при первом запуске). Документ без брони в базу не идёт —
  уходит в уведомление, а не молча в общие заметки.
- Публикация — только при изменении хэша и пройденной валидации. Пустой
  результат, падение ниже порога или просадка больше доли — никогда не
  публикуем, остаётся last-good.
- Ключ Drive и URL с ключом никогда не пишутся в логи.

Ответы клиентам по-прежнему идут из памяти (`get_tours_text`): на каждое
сообщение в Google никто не лазит.
"""

import hashlib
import re
from datetime import date as date_type
from datetime import datetime, timezone

import httpx
from structlog import get_logger

from src.services.tour_loader import _BOOKING_URL_RE, _extract_tour_section

logger = get_logger()

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
GOOGLE_DOC_MIME = "application/vnd.google-apps.document"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
SYNCABLE_MIMES = (GOOGLE_DOC_MIME, DOCX_MIME)
HTTP_TIMEOUT = 30
DRIVE_READONLY_SCOPE = "https://www.googleapis.com/auth/drive.readonly"

# Маркеры, после которых в документе идёт служебный хвост (дисклеймер,
# реквизиты, телефоны). В базе их нет (проверено: ЧУП/телефонов в базе нет),
# в базу не тащим.
_FOOTER_MARKERS = ("Туристическая компания", "ЧУП")


def api_key_auth(api_key: str):
    """apply_auth для API-ключа: ключ — параметром запроса."""

    def apply(params: dict, headers: dict) -> None:
        params["key"] = api_key

    return apply


class ServiceAccountAuth:
    """apply_auth для сервисного аккаунта: Bearer-токен в заголовке.

    Токен кэшируется внутри объекта и обновляется по истечении — один объект
    на воркер, не пересоздавать на каждый тик. Приватный ключ из файла никуда
    не пишется и не логируется.
    """

    def __init__(self, credentials_path: str):
        from google.oauth2 import service_account

        self._creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=[DRIVE_READONLY_SCOPE]
        )

    def apply(self, params: dict, headers: dict) -> None:
        from google.auth.transport.requests import Request

        if not self._creds.valid:
            self._creds.refresh(Request())
        headers["Authorization"] = f"Bearer {self._creds.token}"


def make_auth_provider(credentials_file: str = "", api_key: str = ""):
    """Выбрать способ авторизации. Файл сервисного аккаунта в приоритете.

    Возвращает apply_auth(params, headers) или None, если настраивать нечего.
    """
    if credentials_file:
        return ServiceAccountAuth(credentials_file).apply
    if api_key:
        return api_key_auth(api_key)
    return None


def _redact(params: dict) -> dict:
    """Копия параметров без секретов — для логов."""
    return {k: ("<redacted>" if "key" in k.lower() else v) for k, v in params.items()}


def _call(http_get, url: str, params: dict, apply_auth) -> object:
    """Один GET с подставленной авторизацией. Токен/ключ в логи не пишем."""
    headers: dict = {}
    apply_auth(params, headers)
    return http_get(url, params=params, timeout=HTTP_TIMEOUT, headers=headers)


def list_drive_docs(http_get, folder_id: str, apply_auth) -> list[dict]:
    """Перечислить файлы папки. Возвращает [{id, name, mime, modified}].

    Берём нативные Google Docs и загруженные .docx — оба типа умеем разбирать.
    `http_get` — вызываемый `(url, params, timeout, headers)`, инжектится.
    Бросает `httpx.HTTPError` наружу — ловит вызывающий воркер.
    """
    params = {
        "q": f"'{folder_id}' in parents and trashed = false",
        "fields": "files(id,name,mimeType,modifiedTime)",
        "pageSize": 100,
    }
    resp = _call(http_get, DRIVE_FILES_URL, params, apply_auth)
    resp.raise_for_status()
    files = resp.json().get("files", [])
    docs = [
        {
            "id": f["id"],
            "name": f["name"],
            "mime": f.get("mimeType", ""),
            "modified": f.get("modifiedTime", ""),
        }
        for f in files
        if f.get("mimeType") in SYNCABLE_MIMES and f.get("id") and f.get("name")
    ]
    logger.debug("tour_sync.listed", count=len(docs), params=_redact(params))
    return docs


def export_doc_text(http_get, doc: dict, apply_auth) -> str:
    """Скачать содержимое файла raw-текстом (без обработки).

    Нативный Google Doc — через export в plain text; загруженный .docx —
    через download (`alt=media`) с разбором абзацев той же библиотекой,
    что читает локальные файлы.
    """
    if doc["mime"] == GOOGLE_DOC_MIME:
        params = {"mimeType": "text/plain"}
        resp = _call(http_get, f"{DRIVE_FILES_URL}/{doc['id']}/export", params, apply_auth)
        resp.raise_for_status()
        return resp.text
    params = {"alt": "media"}
    resp = _call(http_get, f"{DRIVE_FILES_URL}/{doc['id']}", params, apply_auth)
    resp.raise_for_status()
    from io import BytesIO

    from docx import Document

    document = Document(BytesIO(resp.content))
    return "\n".join(p.text for p in document.paragraphs)


def normalize_tour_name(name: str) -> str:
    """Каноническое имя для сопоставления: регистр/расширение/пробелы/тире."""
    n = name.lower()
    n = re.sub(r"\.[a-z0-9]+$", "", n)
    n = n.replace("—", "-").replace("–", "-").replace("_", " ")
    n = re.sub(r"\s+", " ", n)
    n = re.sub(r"\s*-\s*", "-", n)
    return n.strip()


def parse_aliases(raw: str) -> dict[str, str]:
    """'A=B;C=D' -> {canon(A): canon(B)}. Связка имён из папки с базой."""
    aliases: dict[str, str] = {}
    for part in (raw or "").split(";"):
        if "=" not in part:
            continue
        left, right = part.split("=", 1)
        if left.strip() and right.strip():
            aliases[normalize_tour_name(left)] = normalize_tour_name(right)
    return aliases


def clean_display_name(name: str) -> str:
    """Имя для заголовка секции: без расширения, без двойных пробелов.

    В папке встречаются «Французский  поцелуй.docx» — такой мусор иначе
    уехал бы в заголовок «=== ТУР: ... ===» и дальше в ответы модели.
    Регистр и смысл не трогаем.
    """
    cleaned = re.sub(r"\.[a-zA-Z0-9]+$", "", name.strip())
    return re.sub(r"\s+", " ", cleaned).strip()


def parse_tour_headers(base_text: str) -> list[str]:
    """Названия туров из готовой базы (для сверки первого запуска)."""
    names: list[str] = []
    for line in base_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("=== ТУР:"):
            names.append(stripped[len("=== ТУР:"):].rstrip("=").strip())
    return names


def normalize_lines(text: str) -> list[str]:
    """BOM долой, пустые строки долой, пробелы в порядок."""
    lines: list[str] = []
    for raw in text.replace("﻿", "").split("\n"):
        line = " ".join(raw.split()).strip()
        if line:
            lines.append(line)
    return lines


def cut_footer(lines: list[str]) -> list[str]:
    """Отрезать служебный хвост документа (дисклеймер, реквизиты)."""
    out: list[str] = []
    for line in lines:
        if line.startswith(_FOOTER_MARKERS):
            break
        out.append(line)
    return out


def seed_bookings_from_text(base_text: str) -> dict[str, str]:
    """Bootstrap: название тура -> ссылка на бронирование из текущей базы.

    Нужен один раз при первом запуске: в Google-документах ссылок на бронь
    нет, а в базе они есть. Дальше бронь наследуется по ID документа.
    """
    bookings: dict[str, str] = {}
    current: str | None = None
    for line in base_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("=== ТУР:"):
            current = stripped[len("=== ТУР:"):].rstrip("=").strip()
        elif current:
            m = _BOOKING_URL_RE.search(stripped)
            if m:
                bookings.setdefault(current, m.group(1))
    return bookings


def _doc_tour_url(doc_id: str) -> str:
    return f"https://docs.google.com/document/d/{doc_id}"


def build_snapshot(
    raws: dict[str, dict],
    carried_bookings: dict[str, str],
    today: date_type | None = None,
) -> tuple[dict, list[str]]:
    """Собрать снапшот из сырых текстов документов.

    `raws`: doc_id -> {name, text}. `carried_bookings`: doc_id -> URL брони.
    Возвращает (snapshot, skipped): skipped — описания пропущенных документов
    для уведомления («без ссылки на бронирование»).
    """
    today = today or date_type.today()
    tours: list[dict] = []
    skipped: list[str] = []

    for doc_id, doc in raws.items():
        lines = cut_footer(normalize_lines(doc["text"]))
        # Приоритет брони: строка внутри документа > перенос по ID из прошлого
        # состояния (в sync_now туда же подмешан bootstrap-подхват по названию
        # из текущей базы — для первого запуска).
        booking = None
        m = _BOOKING_URL_RE.search("\n".join(lines))
        if m:
            booking = m.group(1)
        elif doc_id in carried_bookings:
            booking = carried_bookings[doc_id]
            lines = lines + [f"Ссылка на бронирование - {booking}"]

        if not booking:
            skipped.append(f"{doc['name']} (нет ссылки на бронирование)")
            logger.warning("tour_sync.skipped_no_booking", name=doc["name"])
            continue

        paragraphs = lines + [f"Ссылка на тур - {_doc_tour_url(doc_id)}"]
        section = _extract_tour_section(doc["name"], paragraphs, today=today)
        tours.append(
            {
                "doc_id": doc_id,
                "name": doc["name"],
                "booking_url": booking,
                "modified": doc.get("modified", ""),
                "raw": doc["text"],
                "section": section,
            }
        )

    tours.sort(key=lambda t: t["name"])
    names = [t["name"] for t in tours]
    if len(set(names)) != len(names):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"дублирующиеся названия туров: {dupes}")

    text = "\n\n".join(t["section"] for t in tours)
    snapshot = {
        "tours": [
            {k: t[k] for k in ("doc_id", "name", "booking_url", "modified", "raw")}
            for t in tours
        ],
        "text": text,
        "hash": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    return snapshot, skipped


def validate_snapshot(
    tour_count: int,
    prev_count: int | None,
    min_tours: int,
    max_drop_ratio: float,
) -> tuple[bool, str]:
    """Валидация перед публикацией. Пусто/мало/резкая просадка — отказ."""
    if tour_count == 0:
        return False, "пустой результат (0 туров)"
    if tour_count < min_tours:
        return False, f"туров {tour_count} меньше порога {min_tours}"
    if prev_count and prev_count > 0:
        drop = (prev_count - tour_count) / prev_count
        if drop > max_drop_ratio:
            return False, (
                f"просадка {prev_count} -> {tour_count} "
                f"больше допустимой доли {max_drop_ratio}"
            )
    return True, ""


def _key_lines(section: str, prefix: str) -> str:
    for line in section.split("\n"):
        if line.strip().startswith(prefix):
            return line.strip()
    return ""


def diff_snapshots(old: dict | None, new: dict) -> dict:
    """Что изменилось между сборками (по ID документов)."""
    old_tours = {t["doc_id"]: t for t in (old or {}).get("tours", [])}
    new_secs = {}
    for chunk in new["text"].split("=== ТУР:")[1:]:
        lines = chunk.split("\n")
        name = lines[0].replace("=", "").strip()
        for t in new["tours"]:
            if t["name"] == name:
                # Разделитель "\n\n" между секциями прилипает к хвосту —
                # срезаем, иначе каждая сборка выглядела бы «изменённой».
                new_secs[t["doc_id"]] = ("=== ТУР:" + chunk).rstrip("\n")
                break

    added = [t["name"] for t in new["tours"] if t["doc_id"] not in old_tours]
    removed = [t["name"] for t in old_tours.values() if t["doc_id"] not in {t["doc_id"] for t in new["tours"]}]
    changed: list[str] = []
    for t in new["tours"]:
        doc_id = t["doc_id"]
        if doc_id not in old_tours:
            continue
        old_sec = old_tours[doc_id].get("section", "")
        new_sec = new_secs.get(doc_id, "")
        if old_sec == new_sec:
            continue
        notes: list[str] = []
        if t["name"] != old_tours[doc_id].get("name"):
            notes.append(f"переименован: {old_tours[doc_id].get('name')} -> {t['name']}")
        for prefix, label in (
            ("Сколько стоит:", "цена"),
            ("Когда (", "даты"),
            ("Ссылка на тур:", "ссылка на тур"),
            ("Ссылка на бронирование:", "ссылка на бронь"),
        ):
            a, b = _key_lines(old_sec, prefix), _key_lines(new_sec, prefix)
            if a != b:
                notes.append(f"{label}: {a or '—'} -> {b or '—'}")
        changed.append(f"{t['name']} ({'; '.join(notes) if notes else 'текст'})")
    return {"added": added, "removed": removed, "changed": changed}


def format_diff_message(diff: dict, skipped: list[str]) -> str:
    """Короткое русское уведомление для Telegram."""
    lines = ["🔄 Обновление туров (Google Drive):"]
    if diff["added"]:
        lines.append("➕ Добавлены: " + "; ".join(diff["added"]))
    if diff["removed"]:
        lines.append("➖ Удалены: " + "; ".join(diff["removed"]))
    for c in diff["changed"]:
        lines.append("✏️ " + c)
    for s in skipped:
        lines.append("⚠️ Пропущен (проверьте документ): " + s)
    if len(lines) == 1:
        lines.append("изменений состава нет")
    return "\n".join(lines)


def _resolve_auth(auth):
    """apply_auth из конфига ({credentials_file, api_key}) или готовый callable."""
    if auth is None:
        return None
    if callable(auth):
        return auth
    return make_auth_provider(auth.get("credentials_file", ""), auth.get("api_key", ""))


def sync_now(
    http_get,
    folder_id: str,
    auth,
    prev: dict | None,
    carried_seed_text: str = "",
    aliases: dict | None = None,
    min_tours: int = 1,
    max_drop_ratio: float = 0.5,
    today: date_type | None = None,
) -> tuple[dict | None, dict]:
    """Один проход синхронизации. Исключений наружу не выпускает.

    `auth` — готовый apply_auth-каллбл (удобно в тестах) или словарь
    {credentials_file, api_key}. Возвращает (snapshot|None, info).
    info.status: ok | unchanged | invalid | error | auth_error | disabled.
    При ok в info лежат diff и skipped.
    """
    if not folder_id:
        return None, {"status": "disabled"}
    try:
        apply_auth = _resolve_auth(auth)
    except OSError as exc:
        logger.error("tour_sync.auth_init_failed", error=str(exc)[:120])
        return None, {"status": "auth_error", "reason": "учётные данные Drive недоступны"}
    if apply_auth is None:
        return None, {"status": "disabled"}

    try:
        docs = list_drive_docs(http_get, folder_id, apply_auth)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code if exc.response is not None else 0
        if 400 <= code < 500:
            logger.error("tour_sync.auth_error", status=code)
            return None, {"status": "auth_error", "reason": f"Drive API: HTTP {code}"}
        logger.warning("tour_sync.list_failed", status=code)
        return None, {"status": "error", "reason": f"список папки: HTTP {code}"}
    except httpx.HTTPError as exc:
        logger.warning("tour_sync.list_failed", error=exc.__class__.__name__)
        return None, {"status": "error", "reason": "список папки недоступен"}

    prev_tours = {t["doc_id"]: t for t in (prev or {}).get("tours", [])}
    raws: dict[str, dict] = {}
    skipped_dl: list[str] = []
    for doc in docs:
        display = clean_display_name(doc["name"])
        old = prev_tours.get(doc["id"])
        if old and old.get("modified") == doc["modified"] and old.get("raw"):
            raws[doc["id"]] = {
                "name": display,
                "modified": doc["modified"],
                "text": old["raw"],
            }
            continue
        try:
            text = export_doc_text(http_get, doc, apply_auth)
        except httpx.HTTPError as exc:
            logger.warning(
                "tour_sync.export_failed", name=doc["name"], error=exc.__class__.__name__
            )
            if old and old.get("raw"):
                raws[doc["id"]] = {
                    "name": display,
                    "modified": old.get("modified", ""),
                    "text": old["raw"],
                }
            else:
                skipped_dl.append(f"{display} (не скачался)")
            continue
        raws[doc["id"]] = {
            "name": display,
            "modified": doc["modified"],
            "text": text,
        }

    carried = {doc_id: t["booking_url"] for doc_id, t in prev_tours.items() if t.get("booking_url")}
    seed = seed_bookings_from_text(carried_seed_text) if carried_seed_text else {}
    seed_norm = {normalize_tour_name(k): v for k, v in seed.items()}
    aliases = aliases or {}
    # Подхват брони по названию — только для документов, которых не было
    # в прошлом состоянии (bootstrap при первом запуске). Имена сравниваем
    # в канонической форме: регистр, расширение, пробелы и тире у начальства
    # гуляют («Французский  поцелуй.docx»), а явные расхождения
    # («Эльбрус 2027» vs «Горнолыжный отдых на Эльбрусе») закрываем алиасами.
    for doc_id, doc in raws.items():
        if doc_id in carried:
            continue
        key = normalize_tour_name(doc["name"])
        target = aliases.get(key, key)
        if target in seed_norm:
            carried[doc_id] = seed_norm[target]

    try:
        snapshot, skipped = build_snapshot(raws, carried, today=today)
    except ValueError as exc:
        logger.error("tour_sync.build_failed", error=str(exc))
        return None, {"status": "invalid", "reason": str(exc)}
    skipped = skipped + skipped_dl

    # Первый запуск (снапшота ещё нет): сравниваем с текущей базой из seed —
    # иначе исчезновение туров, которых нет в папке, прошло бы молча.
    # Сопоставление алиас-чувствительное: «Эльбрус 2027» из папки — это
    # «Горнолыжный отдых на Эльбрусе» из базы, а не удаление + добавление.
    base_names: list[str] = []
    if prev is None and carried_seed_text:
        base_names = parse_tour_headers(carried_seed_text)
    if base_names:
        new_mapped = {
            aliases.get(normalize_tour_name(t["name"]), normalize_tour_name(t["name"]))
            for t in snapshot["tours"]
        }
        missing = [
            n for n in base_names if normalize_tour_name(n) not in new_mapped
        ]
    else:
        missing = []

    prev_count = len(prev_tours) if prev else (len(base_names) or None)
    ok, reason = validate_snapshot(len(snapshot["tours"]), prev_count, min_tours, max_drop_ratio)
    if not ok:
        logger.warning("tour_sync.validation_failed", reason=reason)
        return None, {"status": "invalid", "reason": reason}

    if prev and snapshot["hash"] == prev.get("hash"):
        return prev, {"status": "unchanged"}

    diff = diff_snapshots(prev, snapshot)
    for gone in missing:
        if gone not in diff["removed"]:
            diff["removed"].append(f"{gone} (нет в папке)")
    logger.info(
        "tour_sync.built",
        tours=len(snapshot["tours"]),
        chars=len(snapshot["text"]),
        added=len(diff["added"]),
        removed=len(diff["removed"]),
        changed=len(diff["changed"]),
        skipped=len(skipped),
    )
    return snapshot, {"status": "ok", "diff": diff, "skipped": skipped}
