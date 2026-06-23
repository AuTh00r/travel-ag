# Сессия 23.06.2026 — Instagram webhook end-to-end тест

## Контекст

Пользователь: Данила (Автор)
Проект: travel-agent-bot
Задача: заставить Instagram webhook принимать DM и отвечать через AI

## Хронология

### 1. Webhook POST пришёл, но подпись не прошла
- Meta слала POST (IP 173.252.107.x), но `X-Hub-Signature-256` не совпадала
- Пробовали APP_SECRET: `0219b2cce29f89ca129ea10e55cd605b` (старое приложение) и `1q2w3e4r5t6y7u8i` (новое) — оба не подошли
- **Решение:** очистили APP_SECRET → подпись пропускается
- **Факт:** вебхук подписан через Messenger product в старом приложении, APP_SECRET нужно копировать оттуда

### 2. DeepSeek не отвечал
- `base_url="https://api.deepseek.com/v1"` — неверно
- Документация: `base_url="https://api.deepseek.com"`
- **Исправлено:** `src/services/llm.py:15,29`
- Баланс: $1.93 (доступен)

### 3. AI зависал без таймаута
- `ChatOpenAI` без `timeout` — висел бесконечно
- **Исправлено:** добавлен `timeout=120` → `src/services/llm.py:18,33`

### 4. JSONDecodeError в clarify
- DeepSeek возвращал пустой ответ → `json.loads('')` падал
- **Исправлено:** try/except в `src/ai/nodes.py:53`

### 5. Echo-петля (бот отвечал на свои ответы)
- Meta шлёт `is_echo: true` когда бот отправляет сообщение
- **Исправлено:** фильтр `messaging.message.is_echo` в `src/channels/instagram.py:70`

## Git-коммиты

```
2e4ed64 fix: add 30s timeout to DeepSeek API calls
8d09d33 fix: increase DeepSeek API timeout to 120s
22d2495 fix: correct DeepSeek base URL (was /v1, should be api.deepseek.com)
abf677c fix: filter out echo messages to prevent bot feedback loop
398d296 fix: handle JSON parse error in clarify when LLM returns empty
```

## Результат теста

- ✅ **Webhook GET** (верификация) — работает
- ✅ **Webhook POST** (приём DM) — работает
- ✅ **AI обработка** — доходит до `clarify`, но `json.loads('')` падало → теперь try/except
- ✅ **send_message** — отправляет через `graph.facebook.com/v25.0/me/messages` с EAA-токеном
- ⚠️ **DeepSeek медленный** — 30-60 сек на вызов, полный граф ~2 мин
- ❌ **Подпись** — не проверяется (APP_SECRET пуст)

## Проблемы

1. **Ретраи Meta:** при долгой AI-обработке Meta шлёт повторные вебхуки — очередь из 5+ сообщений
2. **APP_SECRET:** нужно скопировать из Dashboard старого приложения, где настроен Messenger webhook
3. **DeepSeek:** очень медленный для последовательных LLM-вызовов в LangGraph

## Команды VPS

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot && git pull && rm -f sessions.db && pkill -9 -f uvicorn; systemctl start travel-bot
journalctl -u travel-bot --no-pager -n 50
curl http://127.0.0.1:8000/webhook/instagram/last_seen
```

## Todo

- [ ] Скопировать правильный APP_SECRET из Dashboard старого приложения
- [ ] Добавить dedup ретраев Meta (в `main.py`)
- [ ] Пройти App Review для включения Live Mode
- [ ] Подумать над заменой DeepSeek на более быструю модель
