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

## Деплой на Timeweb Cloud VPS

### 1. Создать VPS

- Timeweb Cloud → VPS → Ubuntu 24.04, минимум 1GB RAM, 1 vCPU
- После создания записать IP-адрес (например, `201.51.3.72`)
- Сгенерировать SSH-ключ для доступа:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_travelbot -N ""
ssh-copy-id -i ~/.ssh/id_ed25519_travelbot root@<IP-адрес-VPS>
# Или добавить публичный ключ в панели Timeweb Cloud
```

### 2. Развернуть проект

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@<IP-адрес-VPS>

# Python 3.11
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3.11-dev git curl

# Клонировать
git clone https://github.com/AuTh00r/travel-ag.git /opt/travel-agent-bot
cd /opt/travel-agent-bot

# Виртуальное окружение
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Настроить .env
cp .env.example .env
nano .env  # вставить реальные ключи
```

### 5. Настроить DuckDNS (бесплатный домен)

1. Зайти на https://www.duckdns.org
2. Войти через GitHub/Google/Twitter
3. Создать домен (например, `travelagenttest.duckdns.org`)
4. Добавить A-запись → IP вашего VPS
5. Получить токен

Создать скрипт обновления IP `/opt/travel-agent-bot/duckdns.sh`:

```bash
#!/bin/bash
echo url="https://www.duckdns.org/update?domains=<DOMAIN>&token=<TOKEN>&ip=" | \
  curl -s -k -o /dev/null -K -
```

```bash
chmod +x /opt/travel-agent-bot/duckdns.sh

# Добавить в cron (каждые 5 минут)
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/travel-agent-bot/duckdns.sh >/dev/null 2>&1") | crontab -
```

### 6. Настроить Nginx + Let's Encrypt SSL

Создать `/etc/nginx/sites-available/travel-bot`:

```nginx
server {
    listen 80;
    server_name <ВАШ_ДОМЕН>.duckdns.org;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name <ВАШ_ДОМЕН>.duckdns.org;

    ssl_certificate /etc/letsencrypt/live/<ВАШ_ДОМЕН>.duckdns.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/<ВАШ_ДОМЕН>.duckdns.org/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /health {
        access_log off;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Включить сайт
ln -s /etc/nginx/sites-available/travel-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Получить SSL (certbot сам обновит конфиг nginx, если server_name совпадает)
certbot --nginx -d <ВАШ_ДОМЕН>.duckdns.org

# Если certbot не смог автоматически настроить — перезаписать конфиг вручную
# (как указано выше) и перезагрузить nginx
nginx -t && systemctl reload nginx

# Проверить
curl https://<ВАШ_ДОМЕН>.duckdns.org/health
# → {"status": "ok"}
```

### 7. Настройка Instagram Webhook

Webhook URL (требует HTTPS — готов после шага 6):

```
Callback URL: https://<ВАШ_ДОМЕН>.duckdns.org/webhook/instagram
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

### 8. Instagram в Development Mode (приём сообщений до Live Mode)

В **Development Mode** (по умолчанию для новых приложений Meta) Instagram присылает
POST на webhook **только от пользователей, добавленных в App Roles**. Для реальных
клиентов нужно перевести приложение в Live Mode (App Review / Business Verification —
см. `docs/ERROR.md`). Но уже сейчас можно прогнать бота end-to-end с тестерами.

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
curl https://<ВАШ_ДОМЕН>.duckdns.org/webhook/instagram/last_seen
```

> ⚠️ **Важно для прода:** `INSTAGRAM_APP_SECRET` обязан быть задан в `.env` на VPS.
> Без него webhook принимает произвольные POST без проверки подлинности (см. лог
> `instagram.webhook.signature_skipped`). App Secret берётся в App Dashboard →
> Settings → Basic → **App Secret**.

## Структура данных

- **SQLite `data/sessions.db`** — сессии диалогов (создаётся автоматически)
- **ChromaDB `data/chroma/`** — векторная БД FAQ (создаётся при старте из `data/faq/*.txt`)

## Мониторинг

```bash
# Health
curl https://<ВАШ_ДОМЕН>.duckdns.org/health
```

## Обновление кода на VPS

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@<IP-адрес-VPS>

cd /opt/travel-agent-bot
git pull
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -q

# Перезапустить бота
# Если через systemd: systemctl restart travel-bot
# Если через screen/tmux: pkill -f "uvicorn"; nohup .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 &
```
