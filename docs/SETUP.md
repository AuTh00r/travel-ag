# Travel Agent Bot — Установка и деплой

## Требования

- Python 3.11+
- SSH-доступ к VPS (Ubuntu 24.04 LTS)
- Доступ к API: DeepSeek, Meta Graph API (Instagram), Google Sheets, Telegram Bot
- Git
- (Опционально) Docker / Docker Compose

## Локальная разработка

```bash
# 1. Клонировать
git clone https://github.com/AuTh00r/travel-ag.git
cd travel-agent-bot

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить переменные окружения
cp .env.example .env
# Отредактировать .env — заполнить реальные ключи

# 5. Запустить сервер
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 7. Проверить health
curl http://localhost:8000/health
# → {"status": "ok"}

# 8. Тесты
pytest tests/ -q
ruff check src tests
```

Актуальный тестовый набор: 90 тестов в 7 файлах. `pyproject.toml` включает
`asyncio_mode = "auto"`, а `conftest.py` добавляет корень проекта в `sys.path`.
Playwright не требуется — тесты без него.

## Сервер (Windows + Cloudflare Tunnel)

Сервер — Windows-машина с Cloudflare Tunnel. Домен `sundita.online` проброшен
через Cloudflare на `localhost:8000`. SSH-доступ — через `ssh.sundita.online`
с аутентификацией через Cloudflare Access.

### SSH-доступ

Настроен в `~\.ssh\config`:

```
Host sundita-office
  HostName ssh.sundita.online
  User deploy
  IdentityFile ~\.ssh\id_ed25519_travelbot
  ProxyCommand cloudflared access ssh --hostname %h
```

Подключение:

```powershell
ssh sundita-office
```

При первом подключении `cloudflared` откроет браузер для входа через email.
Подробнее — `docs/SSH-REMOTE-ACCESS-SETUP.md`.

### Быстрый деплой

```powershell
.\deploy.ps1
```

Скрипт сам коммитит, пушит, стягивает код на сервере, устанавливает
зависимости, запускает тесты, перезапускает бота и проверяет health.

Параметры:
```powershell
.\deploy.ps1 -SkipTests          # без тестов
.\deploy.ps1 -SkipPush           # без пуша
.\deploy.ps1 -CommitMessage "fix" # свой коммит
```

### Настройка Instagram Webhook

```
Callback URL: https://sundita.online/webhook/instagram
Verify Token: <значение INSTAGRAM_VERIFY_TOKEN из .env>
```

Настроить в **Meta Developer Console**:

1. Dashboard → Instagram → Webhooks
2. Нажать **Subscribe** для `messages`
3. Ввести Callback URL и Verify Token
4. Meta отправит GET-запрос с `hub.challenge` — если verify_token совпадает, верификация пройдёт

**X-Hub-Signature-256:** Бот автоматически проверяет подпись каждого POST-запроса.
Если `INSTAGRAM_APP_SECRET` пустой в `.env` — проверка пропускается (для тестов),
в логах появится предупреждение `instagram.webhook.signature_skipped`.

### Instagram в Development Mode (приём сообщений до Live Mode)

В **Development Mode** (по умолчанию для новых приложений Meta) Instagram присылает
POST на webhook **только от пользователей, добавленных в App Roles**. Для реальных
клиентов нужно перевести приложение в Live Mode (App Review / Business Verification).
Но уже сейчас можно прогнать бота end-to-end с тестерами.

**Что проверить (диагностика):**

1. **Тип приложения** — developers.facebook.com → App Dashboard → Settings → Basic →
   поле **App Type** (`Business` или `Consumer/None`). От этого зависит, нужна ли
   Business Verification для перехода в Live Mode.
2. **Тип Instagram-аккаунта** — Instagram → Settings → Account type and tools →
   должен быть **Business** или **Creator** (Personal не работает с Messaging API).
3. **Подписка webhook** — App Dashboard → Instagram (или Messenger) → Webhooks →
   поле **`messages`** должно быть подписано на callback URL и иметь активный статус.

**Добавление тестеров:**

1. App Dashboard → **Roles → Instagram Testers** → **Add Instagram Tester**
   (указать IG-username, лимит ~15 человек).
2. Каждый тестер должен **принять приглашение** в своём Instagram
   (Settings → Apps and websites) и **разрешить permissions**.
3. IG-аккаунты тестеров должны быть **Business/Creator**.
4. Тестер пишет в DM вашего аккаунта → проверьте в логах, что POST пришёл.

**Проверка кнопкой Test (без реального пользователя):**
- App Dashboard → Webhooks → рядом с полем `messages` кнопка **«Test»** →
  отправит тестовый payload на ваш endpoint. Это проверит весь путь до AI-движка.

**Быстрая проверка, достукивается ли Meta вообще:**

```bash
curl https://sundita.online/webhook/instagram/last_seen
```

> ⚠️ **Важно для прода:** `INSTAGRAM_APP_SECRET` обязан быть задан в `.env` на сервере.
> Без него webhook принимает произвольные POST без проверки подлинности (см. лог
> `instagram.webhook.signature_skipped`). App Secret берётся в App Dashboard →
> Settings → Basic → **App Secret**.

## Структура данных

- **SQLite `data/sessions.db`** — сессии диалогов (создаётся автоматически)
- **ChromaDB `data/chroma/`** — векторная БД FAQ (создаётся при старте из `data/faq/*.txt`)

## Мониторинг

```bash
# Health
curl https://sundita.online/health
```

## Обновление кода на сервере

```powershell
.\deploy.ps1
```

Или вручную:

```powershell
ssh sundita-office "chcp 65001 >nul & cd C:\travel-agent-bot & git pull & .venv\Scripts\pip install -r requirements.txt -q & .venv\Scripts\python -m pytest tests -q & schtasks /run /tn RestartTravelBot"
```
