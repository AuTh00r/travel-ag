# Перенос бота на новый рабочий Meta/Instagram аккаунт

Чек-лист для запуска бота под новым, рабочим Meta Business аккаунтом
(отдельным от личных аккаунтов, на которых собирался прототип). Код и сервер
не меняются — меняется только связка Business Manager → Page → Instagram →
App и соответствующие переменные в `.env`.

> Если позже понадобится юридическая верификация бизнеса или переход в Live
> Mode для реальных клиентов — это отдельные, необязательные для запуска
> шаги, см. ссылки в конце документа.

## Что нужно заранее

- Рабочий email, не привязанный к личному Facebook-аккаунту
- Телефон для верификации Business Manager
- Уже работающий сервер с публичным HTTPS-доступом к
  `/webhook/instagram` (сейчас — офисный сервер, домен и SSL уже настроены;
  этот документ не описывает инфраструктуру, только Meta-аккаунт)

---

## Шаг 1 — Meta Business Manager

1. Зайти на https://business.facebook.com/overview
2. **Create Account**, указать рабочий email
3. Подтвердить email, заполнить название компании

Это портфолио, в которое дальше будут добавлены Страница, Instagram и App —
всё должно создаваться *внутри* него, а не в личном профиле, иначе повторится
текущая ситуация (все объекты висят на личном аккаунте).

---

## Шаг 2 — Facebook Page

1. В Business Manager: **Business Settings → Accounts → Pages → Add →
   Create New Page** (не через facebook.com/pages/create — так Страница сразу
   привязывается к нужному портфолио)
2. Указать название (например, рабочее имя компании)

---

## Шаг 3 — Instagram Business аккаунт

1. Если ещё не создан — зарегистрировать новый Instagram аккаунт под рабочий
   email/телефон
2. Instagram → Настройки → **Переключиться на профессиональный аккаунт** →
   Business
3. Facebook → Настройки Страницы (из шага 2) → **Instagram** →
   **Подключить аккаунт** → войти в новый Instagram, разрешить доступ

---

## Шаг 4 — Meta App

1. https://developers.facebook.com/ → зарегистрироваться под рабочим email
2. **My Apps → Create App**
   - Use case: **Other**
   - App type: **Business**
   - **Business portfolio**: выбрать Business Manager из шага 1 (важно —
     не оставлять "None", иначе приложение снова окажется вне портфолио)
3. Dashboard → **Add Product → Instagram → Set up**
4. **Roles → Instagram Testers → Add Instagram Testers** — добавить себя,
   принять приглашение в Instagram (Settings → Apps and websites)
5. Dashboard → **Instagram → Generate Token** — войти в новый Instagram,
   разрешить. Это **Instagram Token (IGAA...)**
<!-- 6. https://developers.facebook.com/tools/explorer/ → выбрать новое
   приложение → **Get Token → Get Page Access Token** → выбрать новую
   Страницу → запрос `me?fields=id,name` → значение `id` — это **Page ID**         возможно не используется--> 

Подробности каждого под-шага (если что-то не совпадает с UI) — см.
[`docs/ENV-SETUP.md`](./ENV-SETUP.md), раздел «Instagram (Meta Graph API)» —
шаги идентичны, отличается только то, что все действия выполняются под
новым рабочим аккаунтом/портфолио, а не личным.

---

## Шаг 5 — новый `.env`

| Переменная | Что делать |
|---|---|
| `INSTAGRAM_APP_SECRET` | **Новое значение** — Dashboard нового App → Settings → Basic → App Secret |
| `INSTAGRAM_ACCESS_TOKEN` | **Новое значение** — токен из шага 4.5 (IGAA...) |
<!-- | `INSTAGRAM_PAGE_ID` | **Новое значение** — из шага 4.6 |
| `INSTAGRAM_IG_USER_ID` | **Новое значение** — ID нового Instagram-аккаунта (из шага 4.5 или `GET https://graph.instagram.com/me?fields=id,username&access_token=<IG_TOKEN>`) |
| `INSTAGRAM_APP_ID` | **Новое значение** — Dashboard нового App → Settings → Basic → App ID | -->
| `INSTAGRAM_VERIFY_TOKEN` | Можно оставить старое значение или задать любую новую строку — используется только для верификации webhook на своей стороне |
| `DEEPSEEK_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_MANAGER_CHAT_ID` и т.д. | Не меняются — не относятся к Meta-аккаунту |

> Токен из Graph API Explorer (EAA.../IGAA...) короткоживущий (~2 часа). Для
> постоянной работы нужен долгоживущий токен через Business Login — см.
> предупреждение в `docs/ENV-SETUP.md`, раздел «Финальный .env».

---

## Шаг 6 — repoint webhook на сервере

1. На сервере: обновить `.env` новыми значениями из шага 5
2. Перезапустить бота:
   ```bash
   systemctl restart travel-bot
   ```
3. В новом App Dashboard → **Instagram → Webhooks**:
   - Callback URL: `https://<текущий-домен>/webhook/instagram` (тот же, что
     уже используется — сервер и домен не меняются)
   - Verify Token: значение `INSTAGRAM_VERIFY_TOKEN` из `.env`
   - Нажать **Subscribe** для `messages`

Механика самой верификации webhook (что присылает Meta, как это проверяется
кодом) не меняется — см. `docs/SETUP.md`, раздел 7.

---

## Шаг 7 — проверка (Development Mode)

Новое приложение по умолчанию в Development Mode — принимает сообщения
только от тестеров, добавленных в шаге 4.4.

1. Написать сообщение в Direct новому Instagram-аккаунту с тестового профиля
2. Проверить, что запрос дошёл:
   ```bash
   curl https://<текущий-домен>/webhook/instagram/last_seen
   ```
3. Проверить логи на сервере (`journalctl -u travel-bot -n 50 --no-pager`) —
   должны появиться `instagram.message.received` и `instagram.message.sent`
4. Убедиться, что ответ пришёл в нативный Instagram Direct

Подробная диагностика (типы аккаунтов, статус подписки webhook) — см.
`docs/SETUP.md`, раздел 8.

---

## Шаг 8 — когда понадобится реальный трафик (Live Mode)

Всё выше достаточно, чтобы бот работал с тестовыми аккаунтами. Чтобы он
отвечал **любым** клиентам страницы (не только тестерам из Dashboard →
Roles), нужен отдельный, необязательный сразу процесс:

- **App Review (Standard → Advanced Access)** — какие permissions запросить,
  как снять скринкаст, частые причины отказа — см.
  [`docs/APP-REVIEW-GUIDE.md`](./APP-REVIEW-GUIDE.md)
- **Business Verification** — обязательное условие для Advanced Access,
  юридические нюансы (в т.ч. по юрисдикции) — см.
  [`docs/BUSINESS-VERIFICATION-GUIDE.md`](./BUSINESS-VERIFICATION-GUIDE.md)

---

## Итоговый чек-лист сверки

- [ ] Business Manager создан под рабочим email
- [ ] Page создана внутри этого Business Manager
- [ ] Instagram Business аккаунт подключён к Page
- [ ] App создан внутри Business Manager, продукт Instagram добавлен
- [ ] `INSTAGRAM_APP_SECRET`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_PAGE_ID`,
      `INSTAGRAM_IG_USER_ID`, `INSTAGRAM_APP_ID` обновлены в `.env` на сервере
- [ ] `systemctl restart travel-bot` выполнен
- [ ] Webhook подписан на `messages` в новом App Dashboard, Callback URL и
      Verify Token совпадают с `.env`
- [ ] Тестовое сообщение дошло и получен ответ (`last_seen` + логи + Instagram Direct)
