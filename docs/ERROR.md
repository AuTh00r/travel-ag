# Session Log — 22.06.2026

## Что сделано

### 1. Починены тесты Instagram
- `test_receive_valid_message` висел → замокан AI-движок (patch `process_with_ai`)
- **87/87 тестов проходят**

### 2. Instagram Page Token
- Был токен `IGAA...` (Instagram User Token) — не подходил к endpoints
- Через Graph API Explorer получен User Token с permissions: `pages_show_list`, `pages_messaging`, `pages_manage_metadata`
- User Token продлён до 60 дней: `/oauth/access_token?grant_type=fb_exchange_token`
- Из long-lived User Token получен Page Token (EAA...) — **бессрочный** (`expires_at: 0`)
- Токен сохранён в `.env` локально и на VPS (`/opt/travel-agent-bot/.env`)
- На VPS сделан `systemctl restart travel-bot`
- Токен на VPS отправляет ответы через `graph.facebook.com/v21.0/me/messages`

### 3. Instagram Webhook — НЕ РАБОТАЕТ (входящие от клиентов)
- **Проблема:** Webhook-подписка требует **Live mode** приложения Meta, чтобы получать
  сообщения от реальных клиентов. В Development Mode приходят только сообщения от
  пользователей из **App Roles** (тестеры).
- **Live mode** требует **Business Verification** (если тип приложения — Business)
- **Причина блокировки:** SMS для подтверждения не приходит на белорусский номер (BY)
- Webhook GET (верификация) проходит ✅
- POST от Instagram для обычных клиентов не приходит ❌
- **В Nginx логах:** зафиксирована только GET-верификация от `173.252.101.0` (Meta), POST от Meta не был зафиксирован (ожидался только в Live Mode или от тестеров)

## Текущие блокеры

| Проблема | Статус | Решение |
|---|---|---|
| Instagram webhook (входящие от клиентов) | ❌ | Live Mode → App Review (+ Business Verification, если App Type = Business) |
| Instagram webhook (входящие от тестеров) | ✅ готов | Работает в Development Mode для пользователей из App Roles — см. `docs/SETUP.md` §8 |
| Instagram send (исходящие) | ✅ | Page Token (EAA...) работает |
| DeepSeek API | ✅ | Оплачен |
| Google Sheets | ✅ | Работает |
| Telegram уведомления | ✅ | Работает |
| ChromaDB RAG | ✅ | 43 записи FAQ |
| Тесты | ✅ | Проходят |

## План решения (по этапам)

### ЭТАП 1 — Диагностика (~10 мин, без кода)
Определяет дальнейшую стратегию. Выяснить:
1. **Тип приложения** — App Dashboard → Settings → Basic → **App Type**.
   - `Business` → Business Verification обязательна для Live (→ ЭТАП 3).
   - `Consumer/None` → App Review доступен **без** Business Verification (→ ЭТАП 4 напрямую, SMS-проблема отпадает).
2. **Тип IG-аккаунта** `_shelter_0` — должен быть Business/Creator.
3. **Подписка webhook** — поле `messages` подписано и активно.

### ЭТАП 2 — Dev Mode пилот (быстрая победа, ~30 мин, без кода)
Прогнать бота end-to-end с тестерами уже сейчас, не дожидаясь верификации.
Подробно: `docs/SETUP.md` §8. Коротко: App Roles → Instagram Testers → принять приглашение →
проверить кнопкой **Test** в Webhooks → тестер пишет в DM.

### ЭТАП 3 — Обход SMS для Business Verification (если App Type = Business)
По возрастанию затрат:
1. **Email-верификация** (бесплатно) — в Business Settings сменить доставку кода с SMS на email.
2. **Сменить язык аккаунта на English** (бесплатно) — задокументированный фикс 2025.
3. **Виртуальный номер другой страны** (~$1–2) — Onlinesim / SMS-Activate (ЕС/РФ/СНГ).
4. **Тикет в Meta Developer Support** (бесплатно, медленно) — запрос про недоставку SMS в BY.

Где: business.facebook.com → Business Settings → Security Centre → Start verification.

### ЭТАП 4 — App Review (production, ~1–2 нед)
1. App Dashboard → App Review → Permissions and Features → запросить `instagram_manage_messages`
   (и/или `pages_messaging`).
2. Подготовить материалы (скринкаст, use case).
3. После одобрения → переключить приложение в **Live Mode**.

## Что сделано технически (ЭТАП 5, 23.06.2026)
- Усилена диагностика webhook: явный лог `instagram.webhook.signature_skipped` когда
  проверка подписи отключена из-за пустого `INSTAGRAM_APP_SECRET`; `instagram.webhook.received`
  теперь логирует количество сообщений.
- Добавлен диагностический endpoint `GET /webhook/instagram/last_seen` — показывает,
  доставался ли Meta вообще (без чтения логов). In-memory, сбрасывается при рестарте.
- `docs/SETUP.md` §8 — инструкция по Dev Mode пилоту и диагностике.

## Команды VPS
```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
journalctl -u travel-bot -f    # логи бота
systemctl restart travel-bot    # рестарт
certbot certificates            # статус SSL
cd /opt/travel-agent-bot && source .venv/bin/activate && pytest tests/ -v   # тесты

# Быстрая диагностика webhook:
curl https://travelagenttest.duckdns.org/webhook/instagram/last_seen
```

## Напоминания
- Разобраться с Chrome для Playwright (`npx playwright install chrome`)
- DeepSeek — баланс пополнен
- На VPS убедиться, что `INSTAGRAM_APP_SECRET` задан в `.env` (иначе подпись не проверяется)
