---
name: travel-bot-dev
description: >
  Разработка и сопровождение travel-agent-bot: Python/FastAPI, Instagram,
  DeepSeek, SQLite-очереди, DOCX/Google Drive, Telegram, медиа и голос.
  Production — Windows с Cloudflare Tunnel.
---

# Travel Bot Dev

## Источники истины

Начни с `README.md`, Git-статуса и соответствующей `.kiro/specs/`.
Архитектура — `docs/ARCHITECTURE.md`, настройки — `src/config.py` и `.env.example`.
Результаты в `runtime/` датированы и не заменяют свежую проверку сервера.
Августовский контекст — исторический архив `docs/archive/`.

Локальный код, GitHub и production могут различаться: последние релизы
выкладывались отдельными файлами. На момент уборки 4 ноября quiet-window
выложен, N42 SDK/deadline остаётся локальным. Сверяй последующие спеки.

## Компоненты

- `src/main.py`, `src/channels/instagram.py` — ingress, dispatch, сообщения.
- `src/db/` — SQLite-сессии, inbound, pending_messages, manager_tasks, receipts.
- `src/services/inbound_recovery.py` — восстановление и сверка.
- `src/services/llm.py`, `handoff_review.py`, `model_failure.py` — модель и сбои.
- `src/services/tour_loader.py`, `tour_sync.py` — DOCX/Google Drive, last-good.
- `src/db/faq_db.py` — согласованные TXT; без них поиск FAQ отключён.
- `src/services/story_media.py`, `ad_media.py`, `voice_media.py`,
  `gigaam_worker.py` — медиа и отдельный голосовой runtime.
- `src/services/telegram_notify.py` — уведомления и подтверждения доставки.

LangGraph отсутствует. Основной AI-проход имеет ограниченные попытки,
handoff-review — отдельную проверку: абсолютный single-call не гарантируется.
Non-text не имеет одного универсального fallback: учитываются тип, текст,
реклама, источник, флаги и takeover. Story mention/unsupported_type имеют
отдельный silent-handoff путь. Не дублировать полную схему из архитектуры.

## Ограничения

- Промпты на русском, настройки через Pydantic, structlog, импорты от `src.`.
- Сохранять dedup MID, очереди, receipts, takeover и бюджет попыток.
- Не расширять production-правки за границы утверждённой спеки.
- Не сбрасывать SQLite, лимиты или takeover без отдельного разрешения.
- Не делать реальные AI/Graph/Telegram вызовы вместо offline-тестов.
- Не печатать `.env`, credentials, токены и клиентскую историю.
- Коммит, push и deployment — только по запросу.
- На Mac пересоздать `.venv`; GigaAM держать в отдельном окружении.
- Story/video содержит жёсткий Windows PowerShell-путь: нужна отдельная адаптация.
- В текущем дереве нет Dockerfile, Compose и `google_sheets.py`.

## Проверки

Из выбранного основного окружения:

```bash
python -m pytest tests/ -q
python -m ruff check src tests
```

Состав тестов: `python -m pytest tests/ --collect-only -q`.
`conftest.py` изолирует SQLite/httpx и содержит Playwright fixtures; сохранять изоляцию.
`black` изменяет файлы; массовое форматирование не входит в перенос.

Полный запуск с рабочими ключами может включить фоновые отправки.
Сначала тестовые подключения и копия данных. Windows media — без reload
и нескольких workers. Deployment описан в `docs/DEPLOY.md`.

## Документация

- `docs/SETUP.md` — окружение и локальный старт.
- `docs/DEVELOPMENT.md` — профильные проверки.
- `docs/ENV-SETUP.md` — настройки и приватные данные.
- `docs/CODEX-WINDOWS-TO-MAC.md` — перенос.
- `data/faq/README.md` — правила подтверждённых FAQ.

Старые шаблоны в `references/`, если присутствуют, сверять с кодом и спекой;
они не определяют текущий runtime.
