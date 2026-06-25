# Сессия: 25.06.2026 (поздняя) — Manager takeover + fix ответов

## Что сделано

### 1. Manager takeover — пауза бота при ответе менеджера (`WORK-PLAN-manager-takeover.md`)

| Задача | Файл | Статус |
|--------|------|--------|
| Настройки `instagram_app_id`, `manager_takeover_ttl_minutes` | `src/config.py`, `.env.example` | ✅ |
| `manager_last_at` в сессии, `is_manager_active()` | `src/db/sessions.py` | ✅ |
| `_sent_mids` set, `is_own_message()`, парсинг эхо в `receive_message()` | `src/channels/instagram.py` | ✅ |
| `_mark_manager_active()`, гейт паузы в `process_with_ai()` | `src/main.py` | ✅ |
| `POST /api/admin/reset-takeover/{client_id}` | `src/main.py` | ✅ |
| Обновлён `ChannelBase.handle_webhook` → `list[dict]` | `src/channels/base.py` | ✅ |

**Ключевое решение:** сообщения клиента во время паузы НЕ сохраняются в историю (исправлено после теста).

### 2. Исправление ответов бота

| Проблема | Решение |
|----------|---------|
| Сообщения обрезались из-за лимита 1000 символов | `_split_reply()` — авторазбивка на несколько сообщений по границам предложений |
| Ссылка на тур зарыта в конце 3000+ символов | `_extract_tour_section()` — ссылка наверху, ключевые поля следом |
| Показывал 3 из 5 туров | Снят лимит «2-3 тура» → «все подходящие» |
| Представлялся «Анастасия» | «ассистент менеджера, не представляйся по имени» |
| Нет ссылок в ответе | Усилено: «скопируй ссылку целиком из поля Ссылка на тур» |

### 3. Промпт — 3 итерации (`src/ai/prompts.py`)

```
ae22e61 — «не знаю»: одно предложение + обязательный ===МЕНЕДЖЕР===
f900968 — «не знаю»: передать менеджеру, а не «позвоните нам»
f132bbc — запрет галлюцинаций, краткие описания туров (1-2 предложения)
```

## Коммиты

```
ae22e61 fix(prompt): don't know -> обязательный ===МЕНЕДЖЕР===, без воды
f900968 fix(prompt): redirect to manager, not phone call
f132bbc fix(prompt): no hallucination, brief tour descriptions
3a1b3de fix: don't save user history during manager takeover pause
1a6acaf feat(admin): add reset-takeover endpoint for manual bot reactivation
db9a84f fix: tour links on top, multi-message splitting, assistant identity
5d3e259 test: cover manager takeover (echo classification, pause gate, TTL)
af09f0e feat(main): pause bot when a human manager replies in the chat
90727f0 feat(instagram): parse echo events, track bot-sent mids
0328ca9 feat(sessions): add manager_last_at + is_manager_active helper
fb6cac5 feat(config): add manager takeover TTL and app_id settings
```

## Что надо протестировать

1. **«Не знаю» → менеджер:** написать боту запрос, которого нет в базе туров (например, «тур на Марс»). Ожидание: одно короткое предложение + приход уведомления менеджеру в Telegram
2. **Краткое описание тура:** спросить про конкретный тур (например, «расскажи про Французский поцелуй»). Ожидание: ссылка + 1-2 предложения, без перечисления всех экскурсий
3. **Мульти-отправка:** попросить показать все туры (>3). Ожидание: несколько сообщений от бота
4. **Ссылка есть:** проверить, что в каждом ответе с туром присутствует `https://docs.google.com/document/d/...`
5. **Manager takeover:** ответить клиенту из инбокса Meta, затем написать от клиента. Ожидание: пауза (skip_llm), потом сбросить через `POST /api/admin/reset-takeover/{id}` — бот снова отвечает с контекстом из истории менеджера
6. **Сброс сессии:** после теста 5 — проверить, что сообщения клиента во время паузы НЕ сохранились в истории
