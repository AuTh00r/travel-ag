# Meta App Review — гайд для Travel Bot

> **Обновлено после проверки реального Dashboard (см. раздел 0.1):** у бота сейчас
> **Standard Access**, весь текущий трафик (1.69 тыс. вызовов `instagram_manage_messages`
> за 30 дней) идёт от аккаунтов с ролью на приложении — это нормально, review для
> Standard Access не требуется в принципе. App Review нужен, только когда встаёт
> вопрос **Advanced Access** — то есть отвечать людям без роли в приложении.

---

## 0. Что означает твой список разрешений

Ты прислал список из App Dashboard → App Review → Permissions and Features:

| Permission | Вызовов/30дн | Что значит "Активно" здесь |
|---|---|---|
| `pages_manage_metadata` | 1.696 тыс. | Standard Access, работает без review — подписка на Page webhooks |
| `pages_messaging` | 1.695 тыс. | Standard Access — доступ к перепискам Страницы в Messenger |
| `instagram_manage_messages` | 1.69 тыс. | Standard Access — чтение/ответ в Instagram Direct (Facebook Login ветка) |
| `instagram_business_manage_messages` | 547 | Standard Access — та же функция, но Instagram Login ветка |
| Page Public Metadata Access | 6 | Feature, не permission — публичные метаданные страницы |
| Business Asset User Profile Access | 5 | Feature — id/name/picture пользователей, взаимодействующих с бизнес-объектами |

> **Подтверждено живой проверкой через Graph API (2026-07-07), см. раздел 0.2** —
> вся реальная доставка сообщений идёт через ОДНУ схему (Facebook Login /
> Page-webhook), 547 вызовов `instagram_business_manage_messages` — вероятно,
> остаточный след более раннего тестирования второй ветки, не активный код-путь.

**Ключевой факт из документации Meta:** Standard Access выдаётся автоматически,
без какого-либо App Review, но работает **только для людей с ролью на
приложении** (admin/developer/tester в Dashboard → Roles). Статус
"Проверка приложения не запрошена" — это НЕ недоделанный шаг с твоей стороны,
это ожидаемое состояние для Standard Access. Твои 1.69 тыс. вызовов в месяц —
скорее всего, это переписка с тестовым/твоим собственным Instagram-аккаунтом,
у которого такая роль есть.

**App Review нужен только для одного перехода:** Standard → Advanced Access,
и это нужно, только если ты хочешь, чтобы бот отвечал **любым** клиентам
страницы — людям без роли в приложении.

### 0.1 Первое, что нужно выяснить самому — реально ли уже нужен переход

Прежде чем готовить submission, ответь себе на вопрос:

**Бот прямо сейчас отвечает только тебе/тестировщикам, или уже реальным
клиентам страницы (не из Dashboard → Roles)?**

- Если только тестировщикам — 1.69 тыс. вызовов это подтверждают, и Advanced
  Access тебе физически не нужен, пока не начнёшь запускать бота на реальных
  клиентов. Можно ничего не подавать прямо сейчас.
- Если бот уже отвечает реальным клиентам страницы (не только тестировщикам) —
  это значит, **либо** у тех клиентов как-то тоже есть роль в приложении
  (маловероятно и не масштабируется), **либо** где-то уже есть Advanced Access
  (тогда странно видеть "Проверка приложения не запрошена"), **либо** бот
  технически работает, но формально это использование за пределами Standard
  Access — стоит уточнить в Meta Business Help Center, это не то, что можно
  корректно диагностировать со стороны кода.

**Проверить в Dashboard:** App Dashboard → Roles → People with roles — сверить
список с реальными клиентами, которым бот отвечает.

### 0.2 Реальная схема — проверено вживую через Graph API (2026-07-07)

Вместо гадания по UI, состояние проверено прямыми вызовами Graph API с сервера
(токен из `.env`, `src/config.py: instagram_access_token`). Вот что подтверждено:

```
Facebook Page:            1176392008892202  ("Test travel Bot")
  └─ Instagram Business:   17841437870938776  (@_shelter_0)

App-level webhook subscriptions (GET /{app_id}/subscriptions):
  object=instagram → callback: sundita.online/webhook/instagram → active: true → fields: [messages]
  object=page      → callback: sundita.online/webhook/instagram → active: true → fields: [messages]

Page-level subscription (GET /{page_id}/subscribed_apps):
  app: "Travel Bot Test1" (1548133150338782) → subscribed_fields: [messages, name]
```

**Вывод:** оба объекта подписки (`instagram` и `page`) указывают на один и тот
же callback URL и активно используются одновременно — это нормальная схема для
Instagram Messaging через Facebook Page, а не дублирование одного и того же
двумя способами. Оба объекта нужны реальной доставке: `object=page` покрывает
базовую доставку, `object=instagram` — Instagram-специфичные события (echo от
менеджера, вложения, story replies, referral) — код в `src/channels/instagram.py`
(`is_echo`, `_extract_non_text_metadata`) явно рассчитан на такие события.

**Проверено на практике:** отключение галочки `messages` в UI-вкладке
Instagram → Webhooks (и повторная отписка на уровне страницы) **не изменило**
состояние ни `object=instagram`, ни `object=page` при повторных проверках через
API — оба остались `active: true`. Бот продолжил отвечать в штатном режиме
(подтверждено живым сообщением в Direct). Похоже, эти конкретные переключатели
в UI относятся к другому, не связанному с боевой доставкой места в Dashboard —
если понадобится реально отключить какую-то из подписок, менять нужно именно
объекты выше (`/{app_id}/subscriptions` или `/{page_id}/subscribed_apps`), а
не полагаться на визуальные тумблеры без проверки через API после изменения.

**Про 547 вызовов `instagram_business_manage_messages`:** живая проверка не
нашла второго активного code path (`graph.instagram.com` нигде не вызывается,
и в App-level subscriptions есть только `graph.facebook.com`-совместимая схема).
Похоже на остаточный след раннего тестирования "API setup with Instagram Login"
(ты вспоминал, что где-то в начале Instagram-путь "не работал", а заработало
только после подключения Messenger — это ровно то же самое, что видно в API).
Мёртвый вес, не требует отдельного запроса Advanced Access.

---

## 1. Какая у нас ветка API

По коду (`src/channels/instagram.py`) бот использует:

- `BASE_URL = https://graph.facebook.com/v25.0`
- Отправка: `POST /me/messages` с Page/IG access token
- Получение: webhook `POST /webhook/instagram`
- Профиль отправителя: `GET /{sender_id}?fields=name,username`

Это **Instagram API with Facebook Login** — permissions без `business_` в имени
(`instagram_manage_messages`, `pages_messaging`, `pages_manage_metadata`).
Подтверждено разделом 0.2 — единственная активная боевая схема.

---

## 2. Если Advanced Access всё же нужен — что запрашивать

Исходя из кода и твоего списка активных permissions:

| Permission | Зачем боту | Включать в submission? |
|---|---|---|
| `instagram_basic` | Базовые метаданные аккаунта — обычно зависимость `instagram_manage_messages` | Да, если Dashboard попросит как зависимость |
| `instagram_manage_messages` | Основной — чтение/отправка Direct-сообщений | Да, основной запрос |
| `pages_show_list` | Список Facebook-страниц — зависимость для связки Страница↔Instagram | Да (если Dashboard требует) |
| `pages_read_engagement` | Ещё одна типовая зависимость `instagram_manage_messages` | Да (если Dashboard требует) |
| `pages_messaging` | Активен (1.695 тыс.) — подтверждено разделом 0.2: `object=page` webhook subscription — часть боевой доставки | Да, включить |
| `pages_manage_metadata` | Активен (1.696 тыс.) — подписка на Page webhooks (`subscribed_apps`), подтверждено разделом 0.2 | Да, включить |
| `human_agent` | Ответ за пределами 24-часового окна | Опционально, см. раздел 3 |

**Подтверждено (раздел 0.2):** `pages_messaging` и `pages_manage_metadata` в коде
`src/channels/instagram.py` явно не вызываются напрямую (нет Messenger Send API
или Page webhook management endpoints) — они активированы автоматически как
часть подписки на Instagram-webhooks через Page (`object=page` в
`/{app_id}/subscriptions`, `subscribed_apps` на самой Странице). Это реальная,
живая зависимость боевой доставки, не мёртвый код. В submission их нужно
описать именно как platform-dependency, не выдумывая отдельное прямое
использование — см. готовую формулировку в разделе 6.

### Правило Meta про зависимости

Если Dashboard подсвечивает permission как зависимость — включай его в submission
целиком, не пытайся подать только `instagram_manage_messages` в одиночку.

### Нужен ли `human_agent`?

В коде есть `manager_takeover_ttl_minutes` (по умолчанию 10080 мин = 7 дней) —
логика "живой менеджер взял чат на себя". Это не то же самое, что ответ клиенту
позже 24 часов от самого бота.

- Если бот всегда успевает ответить в течение 24ч — не запрашивай, Meta
  отклонит permission, который не может протестировать в деле.
- Если бывают случаи ответа позже (ручной ответ менеджера из Telegram спустя
  сутки, или довозка `pending_messages` после долгого сбоя API) — тогда нужен,
  и скринкаст должен показывать именно такой сценарий.

**Рекомендация:** не запрашивать в первом заходе, добавить отдельным review
позже, если появится реальный сценарий.

---

## 3. Обязательные условия ДО подачи заявки (если решишь, что Advanced Access нужен)

Официальный порядок из документации Meta (App Settings → Business Verification →
Data Handling Questions → App Verification → Permissions Review):

- [ ] **App icon** 1024×1024px, под Basic Settings
- [ ] **Privacy Policy URL** — публично доступная страница (например, `sundita.online/privacy`)
- [ ] **App category** — реалистичная категория (например, Business)
- [ ] **Business email** в Developer Settings
- [ ] Список платформ, на которых работает приложение (у нас — website/API,
      без нативного мобильного клиента)
- [ ] Приложение должно **тестироваться извне** — `sundita.online` уже доступен
      через Cloudflare Tunnel, это ок
- [ ] **Хотя бы один вызов API с запрашиваемым permission за последние 30 дней**
      перед подачей — это официальное требование (не просто "когда-то был
      вызов"). У нас `instagram_manage_messages` активно используется прямо
      сейчас (1.69 тыс. вызовов/30дн, см. раздел 0) — условие уже выполнено,
      но помнить об этом при повторной подаче после долгого перерыва.
- [ ] **Business Verification** в Meta Business Manager → Security Center —
      обязательна для Advanced Access permissions (с июня 2023 это официальное
      требование Meta, не опционально). Требует официальные документы компании,
      может занять дольше самого App Review. **Начинать заранее**, параллельно
      с подготовкой скринкаста. **У нас отдельная сложность — юрлицо сейчас
      привязано к личным аккаунтам, планируется переезд на рабочую компанию,
      юрисдикция Беларусь имеет свои нюансы (санкционный контекст).**
      Подробный разбор вариантов и техническая миграция Page/Instagram/App
      на новый Business Manager — см.
      [`docs/BUSINESS-VERIFICATION-GUIDE.md`](./BUSINESS-VERIFICATION-GUIDE.md).
- [ ] **Data Handling questionnaire** — появляется только **после** прохождения
      Business Verification, перед вводом инструкций для тестирования. Описать,
      какие данные бот собирает (переписка, username, номер телефона при
      эскалации) и как обрабатывает (хранение в `src/db/sessions.py`, передача
      в Telegram при эскалации)
- [ ] **Не завершать сборку/менять приложение после подачи** — правки в Basic/
      Advanced Settings во время review могут вызвать повторную проверку с нуля

---

## 4. Пошаговая подача заявки

1. **App Dashboard → Products → Instagram → API setup with Facebook Login**
   (сначала проверь по разделу 1, действительно ли это единственный подключённый продукт)
2. Раздел **"Complete app review"** → раскрыть
3. Просмотреть список permissions — Dashboard сам предложит зависимости
4. **Edit** → 3 блока:
   - **App Settings** — иконка, privacy policy, категория
   - **App Verification** — инструкция ревьюеру, как протестировать бота
     (у бота нет UI логина — объясни, что нужно написать сообщение тестовому
     Instagram-аккаунту напрямую и посмотреть на автоответ)
   - **Permission usage** — текст под каждый permission (шаблоны в разделе 6)
5. Скринкаст под каждый permission (раздел 5)
6. Отправить → **по официальным данным Meta (Best Practices) решение обычно
   приходит примерно через неделю** после подачи и принятия условий (не
   2-4 недели, как оценивали сторонние источники — это была неточность в
   более раннем черновике гайда). На практике сроки могут отличаться,
   особенно если требуется дополнительная Business Verification.
7. **НЕ переключать приложение в Live до получения решения** — Meta прямо
   предупреждает: преждевременный переход в Live может заблокировать текущих
   пользователей с ролями на приложении и раскрыть тестовые dev-данные.

---

## 5. Что снимать на скринкаст

Официальные требования Meta (Best Practices):
- UI — на английском, если возможно; иначе добавлять субтитры/тултипы,
  чтобы неанглоязычный флоу был понятен
- Подписывать неочевидные кнопки/элементы UI — ревьюер должен понимать,
  на что кликает
- **Разрешение 1080p и выше**
- **Показать сам момент выдачи разрешения** ("user granting your app each
  permission"), затем — как приложение реально использует это разрешение
- **Предпочитать действия мышью, не горячие клавиши** — скрытые нажатия
  клавиш нельзя проверить на видео
- Захватывать только релевантное окно/приложение; можно снизить разрешение
  экрана и увеличить курсор для ясности
- **Звук не нужен** — ревьюеры его не слушают
- Достаточно бесплатных инструментов (QuickTime/OBS + iMovie для монтажа) —
  платные (Camtasia/Snagit) не обязательны
- Не включать реальные учётные данные Instagram — только тестовые
- **Не прикладывать скриншот только из нативного Instagram inbox** — Meta
  явно отклоняет такое как единственное доказательство. Нужно показать
  отправку именно со стороны приложения (лог/терминал), а нативный инбокс —
  только как подтверждение результата.
- **Не копировать одно и то же обоснование между разными permissions** —
  Meta явно требует отдельный, специфичный текст под каждый (см. раздел 6,
  вопросы для самопроверки: как это разрешение полезно пользователю, зачем
  оно нужно для работы приложения, что приложение делает с данными, что
  сломается без него)

### Сценарий для `instagram_manage_messages`:

1. Лог входящего сообщения на `/webhook/instagram` (`instagram.message.received`)
2. Лог отправки ответа (`instagram.message.sent`, `recipient_id`)
3. Переключиться на нативный Instagram тестового пользователя — показать,
   что ответ пришёл
4. Сгенерированный cURL из Meta App Dashboard → Instagram → API Integration
   Helper — Meta прямо требует это как доказательство интеграции через
   официальный API

### Для остальных (`instagram_basic`, `pages_show_list`, `pages_read_engagement`,
`pages_messaging`, `pages_manage_metadata`):

Обычно достаточно показать flow подключения — как приложение получает Page
Access Token через связку Facebook-страница ↔ Instagram (последовательность
из `docs/ENV-SETUP.md`, разделы 4-9), плюс один успешный вызов
`GET /me?fields=id,name`.

---

## 6. Шаблоны текста "How will your app use this permission"

Актуализировано 6 сентября 2026 года для приложения **Travel-agent-bot-new**
(`1133220645701291`), собственного аккаунта **@sundita.travel** и интеграции
**Instagram Messaging через Facebook Login**. Ниже — отдельный текст для каждого
из шести разрешений текущей заявки. Исторические рекомендации этого гайда о
включении `pages_messaging` не применять к этой заявке: Facebook Messenger бот
не обслуживает. Не запрашивать `instagram_business_*` другой ветки входа или
Human Agent для автоматических ответов.

Это описания назначения разрешений, а не замена скринкасту и инструкции для
ревьюера. Подключение выполняет администратор собственного бизнеса; не описывать
несуществующий публичный интерфейс подключения сторонних компаний. Токены и
секреты на скринкасте не показывать.

**`instagram_basic`:**
> Travel-agent-bot-new is an automated customer support assistant for Sandita
> Travel Agency's own Instagram professional account, @sundita.travel. We use
> instagram_basic to identify the professional Instagram account linked to our
> Facebook Page and as a required permission for the Instagram User Profile API.
> Together with the other required permissions, this allows our backend to
> retrieve the name and username of a customer who has messaged our account, so
> our staff can identify the conversation when human assistance is needed. We
> do not use this permission to publish content or collect profiles of people
> who have not interacted with our business.

**`instagram_manage_messages`:**
> Our app receives and replies to Direct Messages that customers send to
> @sundita.travel, Sandita Travel Agency's own Instagram account. Incoming
> messages arrive at our backend through Meta webhooks. The backend uses our
> tour catalog and FAQ with DeepSeek to generate an answer, then sends the
> response to the same customer through the Instagram Send API. Customers can
> ask about tours, prices, dates, or request a human manager. When human
> assistance is needed, the app notifies our staff through a private Telegram
> channel with the relevant conversation context and any contact details the
> customer voluntarily supplied. This permission is essential to receive the
> customer's request and deliver our reply. Our use case is customer-initiated
> support, not unsolicited promotional messaging.

**`pages_show_list`:**
> During administrator setup, we use pages_show_list to retrieve the Facebook
> Pages available to the authorized administrator through GET /me/accounts.
> This lets us identify Sandita's own Facebook Page and obtain the Page access
> token for the Page linked to @sundita.travel. Selecting the correct Page
> ensures that customer support messages are processed for the intended
> Instagram business account. We do not aggregate Page lists or use them for
> advertising. This permission is also listed among the requirements for the
> Instagram User Profile API used by our backend.

**`pages_read_engagement`:**
> We request pages_read_engagement because Meta lists it as a required
> permission for the Instagram User Profile API in our Facebook Login
> integration. After a customer messages @sundita.travel, our backend calls
> GET /<INSTAGRAM_SCOPED_USER_ID>?fields=name,username to identify that
> conversation for internal customer support and handoff to our staff. We do
> not use this permission to analyze Facebook Page engagement, collect
> followers, or build marketing audiences. Without this required permission,
> the profile lookup used to identify the customer cannot be reliably supported.

**`pages_manage_metadata`:**
> We use pages_manage_metadata to subscribe our app to the messages webhook
> field for Sandita's Facebook Page, which is linked to @sundita.travel. This
> subscription allows our backend to receive Instagram messaging events and
> respond to customer questions. The permission is also a requirement of the
> Instagram User Profile API used to identify customers during support. We do
> not use it to change the Page's public content or manage unrelated Page
> settings. Without the messaging subscription, the assistant cannot receive
> the events that trigger its replies.

**`business_management`:**
> We request business_management as a documented dependency of
> instagram_manage_messages and pages_show_list in our Facebook Login
> integration. The authorized administrator accesses Sandita's own Facebook
> Page and linked Instagram account through our business portfolio. This
> permission supports the administrator's authorization of those business
> assets so the app can obtain the correct Page access token and provide
> Instagram customer support. Our app serves only Sandita's own business; it
> does not onboard unrelated companies, manage advertising campaigns, or modify
> other businesses' assets. Our screencast will show the administrator's
> authorization flow and the requested business permissions.

Основания для списка и обоснований:

- [Instagram Messaging — обзор и необходимые разрешения](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/overview)
- [Instagram User Profile API — требования для name и username](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/features/user-profile)
- [App Review для собственной компании — instagram_manage_messages и зависимость business_management](https://developers.facebook.com/documentation/business-messaging/instagram-messaging/app-review/apps-for-your-own-business)

---

## 7. После одобрения

- [ ] Переключить приложение из **Development** в **Live**
- [ ] Проверить, что `INSTAGRAM_ACCESS_TOKEN` — долгоживущий токен через
      полноценный Business Login (не 2-часовой из Graph API Explorer,
      см. предупреждение в `docs/ENV-SETUP.md`)
- [ ] Privacy policy и data deletion instructions публично доступны
- [ ] Учитывать лимит Business Use Case (BUC) — 200 вызовов/пользователя/час,
      масштабируется с числом активных пользователей (частично покрыто в коде —
      `_check_rate_limit`, `_RATE_LIMIT_CODES` в `src/channels/instagram.py`,
      )

---

## 8. Частые причины отклонения

Из официальной документации Meta (App Review Content / Best Practices):

- **Отсутствует скринкаст хотя бы для одного запрошенного permission/feature**
  — по формулировке Meta, этого одного достаточно, чтобы заблокировать
  одобрение целиком
- Приложение недоделано или недоступно ревьюеру для тестирования — Meta прямо
  пишет: если они не могут получить доступ к приложению вообще, **вся заявка**
  отклоняется целиком; если доступ есть, но конкретную функцию протестировать
  не удаётся — отклоняется только этот permission/feature
- **Одинаковый текст обоснования скопирован между разными permissions** —
  явно запрещено, каждое должно быть индивидуальным
  (см. вопросы для самопроверки в разделе 5)
- Использованы только клавиатурные действия без видимого действия мышью на видео
- Запрошен permission, который приложение фактически не использует — Meta
  тестирует функциональность предметно, отклоняет конкретно то, что не может проверить
- Неполная Business Verification — без неё Advanced Access не выдадут
- Переключение в Live до получения решения по review (см. раздел 4, шаг 7)

Из практики сообщества (не подтверждено официальной документацией, но часто
упоминается в 2025-2026):
- Скринкаст показывает только нативный Instagram inbox без доказательства
  отправки через API приложения
- Нет явного opt-out/отключения бота для пользователя

---

## 9. Вариант C — посредник (Tech Provider / BSP) вместо своего App Review

Есть третий путь, отдельный от "подавать самому" и "не подавать вообще":
подключиться через сервис, у которого **уже есть Advanced Access на его
собственном приложении** — тогда твой бот работает через их API, и Meta
вообще не видит тебя как отдельного заявителя на review.

### 9.1 Как это устроено

Meta официально описывает три типа партнёров для messaging API (документация
дана для WhatsApp, но модель та же для Instagram Messaging): **Solution
Partners**, **Tech Providers**, **Tech Partners**. Практический смысл для
тебя — важна не терминология Meta, а то, что такие сервисы (ManyChat, Wati,
Chatwoot Cloud и другие) **сами прошли Advanced Access под своё приложение**,
и когда ты подключаешь свой Instagram-аккаунт через их дашборд — ты
используешь их уже одобренное приложение, а не создаёшь собственное. Никакого
App Review, никакой Business Verification с твоей стороны не требуется.

**Важное отличие от self-hosted:** если разворачиваешь опенсорсный вариант
такого сервиса (например, self-hosted Chatwoot) — это создаёт **твоё
собственное** Meta-приложение, со Standard Access, и тебе всё равно придётся
проходить review самому. Advanced Access "бесплатно" достаётся только в
managed/cloud-варианте сервиса, не в self-hosted.

### 9.2 Совместимо ли это с текущей архитектурой бота — ключевая проверка

Твой бот сейчас: webhook получает сообщение → отвечает Meta `200` мгновенно →
обрабатывает в фоне через `asyncio.create_task` → LLM-генерация занимает
**~50 секунд** (см. комментарий в `src/main.py`) → только потом отправляет
ответ отдельным вызовом Send API.

Это принципиально важно, потому что у посредников разная модель работы:

| Сервис | Модель ответа | Совместимо с 50-сек LLM? |
|---|---|---|
| **ManyChat** | External Request — синхронный HTTP-вызов из flow, **жёсткий таймаут 10 секунд**, не настраивается | **Нет, без переделки** — если твой бэкенд не ответит за 10 сек, ManyChat считает запрос упавшим и останавливает flow |
| **Chatwoot (Cloud или self-hosted)** | Agent Bot API — Chatwoot шлёт webhook о новом сообщении, твой бэкенд обрабатывает **асинхронно** и отправляет ответ отдельным вызовом "Create New Message" API, когда будет готов | **Да** — архитектурно то же самое, что у тебя уже есть (webhook → фон → отдельный send) |

**Вывод: ManyChat в лоб не подойдёт** без переделки — либо асинхронно
отвечать "ок, думаю" сразу и потом присылать реальный ответ вторым сообщением
через ManyChat Public API (`sendContent`), либо ускорять LLM-пайплайн до
<10 сек (маловероятно для текущей связки DeepSeek + поиск FAQ). **Chatwoot
(именно Cloud, не self-hosted) — совместим по архитектуре без переделки
логики**: твой FastAPI-бэкенд как был "мозгом", принимающим webhook и решающим
когда/что отправить, так и остаётся — просто транспорт (получение/отправка в
Instagram) идёт через уже одобренное приложение Chatwoot вместо твоего
собственного.

### 9.3 Что теряешь при переходе на посредника

- **Контроль над Business Verification вообще не нужен** — это главный плюс
  для твоей ситуации с Беларусью (раздел 0 `docs/BUSINESS-VERIFICATION-GUIDE.md`)
- Но: **зависимость от чужого приложения** — если у посредника заблокируют
  Advanced Access или изменится их App Review статус, это затронет и тебя
  без твоего участия в процессе
- **Стоимость** — Chatwoot Cloud от $19/агент/месяц (Startups plan), это не
  разово, а ежемесячно
- Придётся переписать `src/channels/instagram.py` под API Chatwoot вместо
  прямого `graph.facebook.com` — не тривиально, но логика самого бота
  (`process_with_ai`, эскалация, FAQ) не меняется, меняется только транспортный
  слой

### 9.4 Рекомендация

Не подавать заявку немедленно на любой из вариантов — сначала стоит взвесить:
если Business Verification (вариант A/B из `BUSINESS-VERIFICATION-GUIDE.md`)
кажется рискованной или долгой, вариант C (Chatwoot Cloud конкретно, не
ManyChat) — реалистичная альтернатива, которая снимает юридический вопрос
полностью, ценой ежемесячной подписки и переписывания транспортного слоя.

---

## Источники

- [App Review — Instagram Platform, Meta for Developers](https://developers.facebook.com/docs/instagram-platform/app-review/)
- [App Review — overview page, Meta for Developers](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review)
- [App Review — Content (detailed process)](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/content)
- [App Review — Best Practices / Submission Guide](https://developers.facebook.com/documentation/resp-plat-initiatives/individual-processes/app-review/submission-guide)
- [Permissions Reference — instagram_manage_messages](https://developers.facebook.com/docs/permissions/reference/instagram_manage_messages)
- [Graph API — Access Levels (Standard vs Advanced)](https://developers.facebook.com/docs/graph-api/overview/access-levels/)
- [Instagram App Review — Chatwoot Developer Docs](https://developers.chatwoot.com/self-hosted/instagram-app-review)
- [Meta for Developers — Partners overview (Solution Partners / Tech Providers)](https://developers.facebook.com/documentation/business-messaging/whatsapp/solution-providers/overview)
- [Chatwoot — Agent Bots (async webhook + Create Message API model)](https://www.chatwoot.com/docs/product/others/agent-bots)
- [Chatwoot Pricing](https://www.chatwoot.com/pricing/)
- [Manychat — Dev Tools: External Request (10s timeout)](https://help.manychat.com/hc/en-us/articles/14281285374364-Dev-Tools-External-request)
