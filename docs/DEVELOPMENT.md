# Рабочее окружение

> Актуально на 26.06.2026.

## Локально

Рекомендуемый путь:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Если обычный `python` не найден в PowerShell, укажи полный путь к Python 3.11+
или используй окружение OpenCode, где зависимости уже настроены.

Каноничные команды:

```bash
pytest tests/ -q
ruff check src tests
black src tests
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Актуальный тестовый набор: 130 тестов в 8 файлах:

- `tests/test_api.py`
- `tests/test_engine.py`
- `tests/test_google_sheets.py`
- `tests/test_guard.py`
- `tests/test_instagram.py`
- `tests/test_sessions.py`
- `tests/test_telegram_notify.py`
- `tests/test_tour_search.py`

`pyproject.toml` задаёт `asyncio_mode = "auto"`. `conftest.py` добавляет корень
проекта в `sys.path` и объявляет Playwright fixtures `browser` / `page`.

## Переменные и секреты

Рабочие секреты лежат в `.env` и `credentials.json`; оба файла игнорируются git.
Не коммитить и не копировать их в документацию.

Для прода обязательно заполнить:

- `DEEPSEEK_API_KEY`
- `INSTAGRAM_APP_SECRET`
- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_VERIFY_TOKEN`
- `GOOGLE_SHEETS_CREDENTIALS_FILE`
- `GOOGLE_REQUESTS_SHEET_ID`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_MANAGER_CHAT_ID`

Без `INSTAGRAM_APP_SECRET` webhook принимает POST без проверки подписи. Это
допустимо только локально.

## Git

Основной remote:

```bash
origin https://github.com/AuTh00r/travel-ag.git
```

Базовая проверка перед изменениями:

```bash
git status --short --branch
git log --oneline -5
```

Перед деплоем:

```bash
pytest tests/ -q
ruff check src tests
git add -A
git commit -m "..."
git push origin master
```

## VPS

Быстрые команды и актуальные адреса лежат в `docs/DEPLOY.md`.

Проверка сервиса на сервере:

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot
source .venv/bin/activate
pytest tests/ -q
systemctl status travel-bot --no-pager -l
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/webhook/instagram/last_seen
```

Публичные проверки:

```bash
curl https://travelagenttest.duckdns.org/health
curl https://travelagenttest.duckdns.org/webhook/instagram/last_seen
```



## Ручная проверка non-text обработки

После деплоя на VPS можно проверить через отправку тестового webhook payload:

```bash
# Вложение без текста
curl -X POST https://travelagenttest.duckdns.org/webhook/instagram \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "messaging": [{
        "sender": {"id": "<CLIENT_ID>"},
        "message": {
          "attachments": [{"type": "image"}],
          "mid": "test_mid_nt_1"
        }
      }]
    }]
  }'

# Ответ на историю
curl -X POST https://travelagenttest.duckdns.org/webhook/instagram \
  -H "Content-Type: application/json" \
  -d '{
    "entry": [{
      "messaging": [{
        "sender": {"id": "<CLIENT_ID>"},
        "message": {
          "reply_to": {"mid": "story_mid"},
          "text": "Классный тур!",
          "mid": "test_mid_nt_2"
        }
      }]
    }]
  }'
```

Проверить логи:

```bash
journalctl -u travel-bot -n 100 --no-pager | grep instagram.non_text
```
