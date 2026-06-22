# Travel Agent Bot — Установка и деплой

## Требования

- Python 3.11+
- Docker + Docker Compose (опционально)
- Доступ к API: DeepSeek, Meta Graph API (Instagram), Google Sheets, Telegram Bot

## Локальная разработка

```bash
# 1. Клонировать
git clone <repo>
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

# 5. Подготовить credentials
# Скачать credentials.json из Google Cloud Console (Service Account)
# Поделиться Google Sheets с email Service Account

# 6. Запустить сервер
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# 7. Проверить health
curl http://localhost:8000/health
# → {"status": "ok"}
```

## Docker

```bash
# Сборка и запуск
docker compose up --build -d

# Проверка логов
docker compose logs -f

# Остановка
docker compose down
```

## Деплой на Timeweb Cloud

### 1. Подготовка VPS

```bash
# Подключиться по SSH
ssh root@<IP-адрес-VPS>

# Установить Docker
apt update && apt install -y docker.io docker-compose-plugin

# Установить Git
apt install -y git
```

### 2. Развернуть проект

```bash
# Клонировать
git clone <repo> /opt/travel-agent-bot
cd /opt/travel-agent-bot

# Настроить .env
cp .env.example .env
nano .env  # вставить реальные ключи

# Загрузить credentials.json
nano credentials.json  # вставить содержимое

# Запустить
docker compose up --build -d
```

### 3. Настройка домена и SSL (Timeweb)

1. В панели Timeweb Cloud привязать домен к VPS (DNS A-запись на IP VPS)
2. Установить Nginx как reverse proxy:

```bash
apt install -y nginx certbot python3-certbot-nginx
```

3. Создать конфиг Nginx `/etc/nginx/sites-available/travel-bot`:

```nginx
server {
    listen 80;
    server_name travel.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/travel-bot /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# Получить SSL
certbot --nginx -d travel.example.com
```

### 4. Настройка Instagram Webhook

После деплоя настроить Webhook в Meta Developer Console:

- **Callback URL:** `https://travel.example.com/webhook/instagram`
- **Verify Token:** (значение `INSTAGRAM_VERIFY_TOKEN` из `.env`)
- **Подписки:** `messages`

Для локальной разработки использовать ngrok:

```bash
ngrok http 8000
# → https://xxxx-xx-xx-xx-xx.ngrok-free.app → localhost:8000
```

## Проверка работоспособности

```bash
# Health check
curl https://travel.example.com/health

# Тесты
pytest tests/ -v

# Линтинг
ruff check src/
```

## Переменные окружения (.env)

См. `.env.example` — все обязательные поля с комментариями.

## Структура данных

- **Google Sheets «Туры»** — база доступных туров (читается ботом)
- **Google Sheets «Заявки»** — заявки клиентов (записываются ботом)
- **SQLite `data/sessions.db`** — сессии диалогов (создаётся автоматически)
- **ChromaDB `data/chroma/`** — векторная БД FAQ (создаётся при старте)

## Мониторинг

- Логи: `docker compose logs -f`
- Health: `GET /health`
- Статусы заявок: `GET /api/requests/{client_id}`
- Обновление статуса: `PATCH /api/requests/{client_id}/status`
