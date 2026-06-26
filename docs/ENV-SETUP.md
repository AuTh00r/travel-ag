# Настройка .env — пошаговая инструкция

## DeepSeek API

1. Зайти на https://platform.deepseek.com/api_keys
2. Зарегистрироваться (email + пароль)
3. Нажать **«Create API key»**
4. Скопировать ключ (начинается с `sk-...`)
5. Вставить в `.env`:
   ```
   DEEPSEEK_API_KEY=sk-...
   DEEPSEEK_MODEL=deepseek-chat
   ```

Код использует OpenAI-compatible endpoint DeepSeek через `langchain-openai`.
Модель переключается только переменной `DEEPSEEK_MODEL`; по умолчанию в проекте
используется `deepseek-chat`.

---

## Google Sheets

### 1. Создать проект в Google Cloud Console

- Зайти на https://console.cloud.google.com/
- Нажать **«Create Project»** (например, `travel-agent-bot`)
- Перейти в **APIs & Services** → **Library**
- Найти и включить **Google Sheets API**

### 2. Создать Service Account

- **Credentials** → **Create Credentials** → **Service Account**
- Назвать (например, `travel-bot-sa`) → **Create and Continue**
- Открыть созданный Service Account → вкладка **Keys** → **Add Key** → **Create New Key** → **JSON**
- Скачать `credentials.json`, положить в **корень проекта**

### 3. Создать Google-таблицу

- Зайти на https://sheets.new
- Назвать таблицу (например, `Travel Bot Database`)
- **Лист 1** переименовать в **Туры**
- Создать **Лист 2**, назвать **Заявки**
- Заполнить шапку листа **Туры** (строка 1):

| Название | Направление | Тип | Даты | Цена | Длительность | Ключевые слова | Ссылка | Доступно |
|---|---|---|---|---|---|---|---|---|

- Заполнить шапку листа **Заявки** (строка 1):

| Дата заявки | Имя | Телефон | Email | Направление | Бюджет | Кол-во человек | Выбранный тур | Статус | Источник | Тег |
|---|---|---|---|---|---|---|---|---|---|---|

### 4. Дать доступ Service Account к таблице

- **Настройки доступа** (правая верхняя кнопка)
- Добавить email Service Account (вида `travel-bot-sa@...iam.gserviceaccount.com`)
- Роль: **Редактор**

### 5. Скопировать ID таблицы

Из URL:
```
https://docs.google.com/spreadsheets/d/1YIU2UL__ZiekGnJcfgXPT8sGTYTwof6jPJyxxdRVDHg/
                                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                       ID таблицы
```
Вставить в `.env`:
```
GOOGLE_SHEETS_CREDENTIALS_FILE=credentials.json
GOOGLE_TOURS_SHEET_ID=<ID таблицы>
GOOGLE_REQUESTS_SHEET_ID=<ID таблицы>
```

### 6. Добавить тестовый тур

В лист **Туры** добавить хотя бы одну строку:

| Название | Направление | Тип | Даты | Цена | Длительность | Ключевые слова | Ссылка | Доступно |
|---|---|---|---|---|---|---|---|---|
| Анталья All-Inclusive | Турция, Анталья | Пляжный | 15.06–22.06.2026 | 1200$ | 7 ночей | море, пляж, семья | https://example.com/tour1 | Да |

> **Важно:** колонка «Доступно» обязательна. Без неё бот не видит тур.

---

## Telegram Bot

### 1. Создать бота

1. Открыть Telegram → найти **@BotFather**
2. Написать `/newbot`
3. Ввести название (например, `Travel Agent Notifications`)
4. Ввести username (например, `travel_agent_notify_bot`)
5. Получить токен вида `1234567890:ABCdefGHIjklmNOPqrstUVWxyz-1234567`

### 2. Получить chat_id

1. Написать боту любое сообщение
2. Открыть в браузере:
   ```
   https://api.telegram.org/bot<ТОКЕН>/getUpdates
   ```
3. Найти `"chat":{"id": 123456789, ...}` — скопировать число

### 3. Вставить в .env

```
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVWxyz-1234567
TELEGRAM_MANAGER_CHAT_ID=123456789
```

---

## Instagram (Meta Graph API)

### Быстрый старт — Graph API Explorer

1. Переключить Instagram на **Creator** или **Business** аккаунт:
   - Instagram → Настройки → Переключиться на профессиональный аккаунт → Creator

2. Создать Facebook-страницу:
   - Facebook → **Страницы** → **Создать страницу**
   - Назвать (например, `Test Travel Bot`)

3. Подключить Instagram к странице:
   - Facebook → Настройки страницы → **Instagram** → **Подключить аккаунт**
   - Войти в Instagram, разрешить доступ

4. Зарегистрироваться на https://developers.facebook.com/
   - **My Apps** → **Create App**
   - Название: `Travel Bot Test`
   - Use case: **Other**
   - App type: **Business**

5. Добавить продукт Instagram:
   - В Dashboard → **Add Product** → **Instagram** → **Set up**

6. Настроить тестового аккаунта:
   - **Roles** → **Instagram Testers** → **Add Instagram Testers**
   - Добавить свой Instagram username
   - Принять приглашение в Instagram (Профиль → Настройки → Приложения → Тестировщик)

7. Получить **Instagram Token (IGAA...)**:
   - В Dashboard → **Instagram** → **Generate Token**
   - Войти в Instagram, разрешить

8. Получить **Page ID** и **IG User ID**:

   IG User ID уже есть из шага 7, но можно проверить:
   ```
   GET https://graph.instagram.com/me?fields=id,username&access_token=<IG_TOKEN>
   ```

   Page ID придёт после шага 9.

9. Получить **Page Access Token (EAA...)**:
   - Открыть https://developers.facebook.com/tools/explorer/
   - Выбрать своё приложение (Travel Bot Test)
   - **Get Token** → **Get Page Access Token**
   - Выбрать свою страницу → разрешить
   - Ввести запрос: `me?fields=id,name`
   - Получить `"id": "..."` — это **Page ID**

### Финальный .env

```
INSTAGRAM_APP_SECRET=...        (из Dashboard → Settings → Basic → App Secret)
INSTAGRAM_ACCESS_TOKEN=IGAA... (из шага 7)
INSTAGRAM_VERIFY_TOKEN=test123  (можно любую строку)
INSTAGRAM_PAGE_ID=...           (из шага 9)
INSTAGRAM_IG_USER_ID=...        (из шага 7 или 8)
```

> **Важно:** токен из Graph API Explorer (EAA...) живёт ~2 часа. Для продакшена нужен долгоживущий токен через Business Login.

---

## Проверка

```bash
# Запустить все тесты
pytest tests/ -q

# Линтер
ruff check src tests
```
