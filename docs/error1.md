# ERROR1.md — Контекст сессии диагностики Instagram Webhook

> Сессия от 2026-06-23. Рабочий контекст для продолжения отладки проблемы:
> **Instagram webhook не получает POST-сообщения от Meta.**

---

## 1. Описание проблемы

Бот (travel-agent-bot) запущен на VPS. Instagram webhook подписка активна,
GET-верификация пройдена (`hub.challenge` возвращается), но **POST-сообщения
от Meta не приходят** при отправке DM на аккаунт `_shelter_0` (IG User ID
`17841437870938776`).

**Цель пользователя**: тест бота end-to-end (client DM → AI → bot reply).
Production Live Mode не нужен.

---

## 2. Архитектура канала Instagram

- **Путь API**: Instagram API with Instagram Login (новый путь, НЕ Messenger)
- **Dashboard**: App "Travel Bot Test1", Instagram product
- **Webhook URL**: `https://travelagenttest.duckdns.org/webhook/instagram`
- **Подписка**: `messages` field — активна (зелёный в Dashboard)
- **Сигнатура**: X-Hub-Signature-256 (HMAC-SHA256 через INSTAGRAM_APP_SECRET)

### Важные файлы
- `src/channels/instagram.py:18` — `BASE_URL` (обновлено v21.0 → **v25.0**)
- `src/channels/instagram.py:20-32` — `verify_signature()` (логирует skip если APP_SECRET пуст)
- `src/channels/instagram.py:71-95` — `send_message()` (использует `/me/messages`)
- `src/main.py:19` — `instagram = InstagramChannel()` (глобальный инстанс)
- `src/main.py:95-116` — **NEW**: `GET /webhook/instagram/last_seen` (диагностика)
- `src/main.py:127-160` — POST-роут: обновляет `_last_webhook_at` перед проверкой сигнатуры, логирует `messages=len(messages)`
- `src/config.py:15-20` — настройки Instagram

---

## 3. VPS / деплой

| Параметр | Значение |
|---|---|
| IP | `201.51.3.72` |
| SSH | `ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72` |
| Путь проекта | `/opt/travel-agent-bot` |
| Venv | `/opt/travel-agent-bot/.venv` |
| systemd | `travel-bot.service` |
| Команда запуска | `uvicorn src.main:app --host 0.0.0.0 --port 8000` |
| Домен | `travelagenttest.duckdns.org` (DuckDNS + Let's Encrypt) |
| Nginx | reverse proxy 443/80 → 127.0.0.1:8000 |
| Git remote | `https://github.com/AuTh00r/travel-ag.git` |

### Деплой-цикл
```bash
# локально
git add ... && git commit -m "..." && git push origin master

# на VPS
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot && git pull && systemctl restart travel-bot
journalctl -u travel-bot -f
```

---

## 4. Текущее состояние токена — КРИТИЧЕСКАЯ ПРОБЛЕМА

### Проверенные токены (оба невалидны)

1. **IGAAOhqQ2...ZDZD** (первый, ~130 символов)
   - Ответ Graph API: `Invalid OAuth access token - Cannot parse access token`
   - Status: ❌ ОТКЛОНЁН

2. **IGAAOhqQ2...ZDZD** (второй, ~200 символов, прислал пользователь 2026-06-23)
   - Ответ Graph API: `Invalid OAuth access token - Cannot parse access token`
   - Status: ❌ ОТКЛОНЁН

### Ключевая находка

Токены **начинаются с `IGAAOhqQ2`** — но **Instagram Long-Lived Token обычно начинается с `IGQV1`**.

Подозрение: пользователь копирует **не тот маркер** или **неполный токен**.
Возможные причины:
- Копируется **App Secret** вместо access token
- Копируется короткий/временный код авторизации, а не long-lived token
- Токен отзывается Meta сразу после генерации (при логауте / смене пароля / отзыве app permissions)

### Тестовый запрос (валидирует токен)
```bash
curl 'https://graph.facebook.com/v25.0/me?fields=id,username&access_token=<TOKEN>'
# Ожидаемый ответ при валидном токене:
# {"id":"17841437870938776","username":"_shelter_0"}
```

---

## 5. Что уже сделано в сессии

1. ✅ Заменены `.env` (локально и VPS):
   - `INSTAGRAM_ACCESS_TOKEN` → новый Instagram token
   - `INSTAGRAM_APP_SECRET` → `0219b2cce29f89ca129ea10e55cd605b`
   - `INSTAGRAM_IG_USER_ID` → `17841437870938776`
2. ✅ Обновлена версия API: `v21.0` → `v25.0` (commit `72c3081`)
3. ✅ Задеплоены диагностические эндпоинты (commit `f8109ca`):
   - `GET /webhook/instagram/last_seen`
   - Логирование количества messages в POST
4. ✅ Бот перезапущен на VPS — `active (running)`
5. ❌ Тест POST: **POST не пришёл** (`received_ever: false`)
6. ❌ **Токен невалиден** при проверке через Graph API

---

## 6. Уточнённая диагностика

| # | Гипотеза | Статус |
|---|---|---|
| 1 | Business Verification нужен для теста | ❌ Опровергнута (не нужно в Dev Mode) |
| 2 | Код/тесты сломаны | ❌ Опровергнута (88/88 тестов проходят, код работает) |
| 3 | Старый токен IGAA | ⚠️ Частично верна (токен обновлён, но новый тоже невалиден) |
| 4 | **Токен генерируется неправильно / копируется неполный** | 🔴 АКТИВНАЯ ГИПОТЕЗА |
| 5 | Webhook подписка не активна | ❌ Опровергнута (`messages` подписан) |
| 6 | POST приходит, но отклоняется проверкой сигнатуры | ❌ Опровергнута (`received_ever` остаётся false — POST не доходит до роута) |

**Текущий корневой диагноз**: Instagram Access Token невалиден.
Без валидного токена Meta не завершает привязку аккаунта к приложению,
поэтому webhook POST не отправляется (несмотря на активную подписку).

---

## 7. План следующих действий

### Для пользователя (через Meta Dashboard)

1. **Перейти**: App Dashboard → Instagram → API → "Настройка API"
2. **Проверить статус маркера** у `_shelter_0`:
   - Если показывает кнопку «Сгенерировать маркер» — значит маркера **нет**
   - Если показывает «Управление» / «Manage» — маркер есть, проверить срок действия
3. **Сгенерировать маркер заново**:
   - В появившемся окне скопировать токен **полностью**
   - Токен обычно **длинный** (~200+ символов)
   - Если начинается с `IGAA` — короткий формат, **опасно**
   - Если начинается с `IGQV1` — правильный long-lived token
4. **Отправить токен** для проверки

### Для ассистента (после получения токена)

1. **Проверить токен** через:
   ```bash
   ssh root@201.51.3.72 "curl -s 'https://graph.facebook.com/v25.0/me?fields=id,username&access_token=<TOKEN>'"
   ```
   Ожидаемый ответ: `{"id":"17841437870938776","username":"_shelter_0"}`
2. Если валиден → обновить `.env` на VPS + локально
3. Перезапустить бот
4. Тест DM → проверить `last_seen` и логи

### Альтернативные пути (если токен не удаётся получить)

- **A. Debug Token через Graph API Explorer**: вставить токен в
  https://developers.facebook.com/tools/explorer/ → увидеть detail (type, expires, scopes)
- **B. Использовать Page Token** через **Messenger API for Instagram** (старый путь):
  - Добавить продукт "Messenger" в Dashboard
  - Сгенерировать Page Access Token через Graph API Explorer
  - Изменить `BASE_URL` и endpoint в `instagram.py` на `/me/messages` с Page Token
  - Webhook подписка через Page subscription (а не через Instagram API)
- **C. Использовать другой IG-аккаунт** (не `_shelter_0`) — возможно, проблема в конкретном аккаунте

---

## 8. Команды для проверки на VPS

```bash
# SSH
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72

# Логи в реальном времени
journalctl -u travel-bot -f

# Проверить, приходил ли POST
curl http://127.0.0.1:8000/webhook/instagram/last_seen
# {"received_ever": false, "last_received_at": null}  ← проблема
# {"received_ever": true, "last_received_at": "2026-06-23T..."}  ← работает

# Проверить валидность токена
TOKEN="<токен>"
curl "https://graph.facebook.com/v25.0/me?fields=id,username&access_token=$TOKEN"

# Проверить конфигурацию .env
grep INSTAGRAM_ /opt/travel-agent-bot/.env
```

---

## 9. Git commits в этой сессии

| Hash | Сообщение |
|---|---|
| `72c3081` | `fix: update Instagram API version to v25.0` |
| `f8109ca` | `feat: add webhook POST diagnostics (last_seen endpoint, message logging)` |

---

## 10. Неофициальные теории (требуют проверки)

1. **Двухфакторная аутентификация** на `_shelter_0`: возможно, токен генерируется,
   но отзывается Meta из-за нарушения session flow. Пользователь должен быть
   залогинен в Instagram в том же браузере, где открыт Dashboard.

2. **App permissions**: `_shelter_0` должен быть в App Roles как Tester/Admin,
   **и** пользователь должен подтвердить доступ через OAuth dialog при генерации токена.
   Если просто нажать «Сгенерировать маркер» без подтверждения в IG — токен будет пустым.

3. **Account type**: `_shelter_0` должен быть **Creator** или **Business** аккаунтом.
   Personal account не поддерживает API. (Пользователь упоминал, что переключил в Creator.)

4. **Webhook подписка на App-level**: подписка активна на App, но не привязана
   конкретно к `_shelter_0` (не хватает привязки через генерацию токена).
