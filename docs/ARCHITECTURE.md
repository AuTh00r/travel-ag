# Travel Agent Bot — Архитектура

> Обзор уточнён 4 ноября 2026. LangGraph удалён; основной AI-проход имеет ограниченные попытки, а handoff-review — отдельную ограниченную проверку. Это не гарантия одного сетевого вызова. Датированные секции описывают эволюцию функций; локальный N42 и последняя серверная выкладка различаются — см. [README](../README.md).

## Поток обработки сообщения

Контактная эскалация сохраняет actual input phone; «Суть» — краткое поле Контекст
из того же AI-запроса (1–2 предложения, ≤450 символов), с туром/вопросом/важными
условиями и человеческим описанием источника истории. Полный ответ не копируется.
Невалидная/отсутствующая сводка, конфликт телефона или новый вопрос+телефон дают
bounded fallback выбранного вопроса (≤200) и одного содержательного предложения
парного доставленного ответа (≤160), только до следующего user. ID/URL/телефоны/
служебные метки в модельной сводке отклоняются; история не переписывается.
Новые AI-вызовы отсутствуют. N6 supersedes N5 длинную выдержку.

```
Instagram DM → POST /webhook/instagram (main.py)
  → verify_signature (X-Hub-Signature-256)
  → instagram.receive_message() → список событий:
      kind="user"          → _process_safely → process_with_ai (LLM)
      kind="user_non_text" → _process_non_text_safely (без LLM)
      kind="manager"       → _mark_manager_active (пауза бота)
  → dedup по отдельным mid до объединения + итоговый mid/related_mids (_processed_mids)
  → 200 OK мгновенно (Meta ретраит без 200)
  → manager echo сразу; пользовательские события → 5 с тишины после последнего MID
  → stateless merge → последовательная обработка пакетов одного sender
```

Emoji-ответ на собственную историю не вызывает ответ/AI, но сохраняет exact ID
для следующего plain text пакета на120с (одноразово, sender-scoped, cap10000).
MID резервируется; повтор реакции не продлевает контекст. Snapshot фиксируется
при приёме вопроса, отдельные реакции создают границы merge; соседние plain тексты
одной истории объединяются. Новые media/phone/referral/manager имеют приоритет;
истёкший/invalid/unsupported контекст и shutdown очищаются. Фото/VIDEO проходят
прежний exact resolver и original/10-frame vision. URL/emoji в cache не хранятся.

### Текстовое сообщение (kind="user")

```
  → _process_safely → process_with_ai(sender_id, text):
      manager takeover gate
      is_rate_limited(sender_id)
      check_input(text)
      _get_lock(sender_id)  # per-user lock
      get_session() → history (list[dict])
      get_tours_text()  (глобальный кеш, ~26K токенов из DOCX)
      search_faq(text)  (ChromaDB RAG, top-3)
      instagram.get_username(sender_id)
      build_full_prompt(...)
      llm.ainvoke(messages)  (DeepSeek)
      response_arguments() → _validate_response() → reply / manager
      check_output(clean_reply)
      → session / manager task / intent в SQLite
      → Telegram-уведомление по решению manager, проверка receipt
      save_session()
      instagram.send_message()
```

### Non-text сообщение (kind="user_non_text")

Общий приём вложений (09.10.2026): проверяются контейнеры webhook, MID/ID и
строковый текст. Нестандартный attachment/type получает безопасное `unknown`,
`is_unsupported=true` запрещает media/contact fast-path. Плохой элемент не
прерывает корректных соседей. Неизвестное сообщение с MID сохраняется как
non-text; удаление и служебные события без message игнорируются. Невалидное JSON
возвращает 400 после проверки подписи. Postback использует видимый title и MID,
не исполняет payload и не скачивает URL. Коллектор ждёт пять секунд тишины;
каждое новое сообщение продлевает ожидание, повтор того же MID — нет.

| Входящий контент | Обработка |
|---|---|
| image / video | JPEG/PNG original или по 10 кадров MP4 |
| story_mention | молчаливое уведомление менеджеру, без распознавания/ответа клиенту |
| own story reply | точный ID → фото или 10 video frames, без звука |
| ig_post / share / ig_reel | доступный Graph post/Reel/full mixed carousel + caption |
| template / contact | подтверждённый телефон → текст; пустой generic рядом с текстом игнорируется только в текущем окне |
| file / product / ig_product | менеджеру, в том числе с подписью и контекстом story reply |
| gif / animated_image / sticker | игнорируется с MID dedup, соседние тексты/медиа сохраняются |
| audio | GigaAM при VOICE_MEDIA_ENABLED; ошибка — менеджеру и просьба повторить/написать |
| unknown | безопасный fallback без угадывания содержимого |
| unsupported_type | отдельный silent handoff, без обычного ответа клиенту |
| quick reply / postback | видимый текст, без исполнения payload |

Рекламный referral сохраняет ограниченный заголовок и доступные приватные media
источники отдельно от вопроса клиента, включая голосовой. Заголовок — данные,
не инструкция и не действующие цены. Предоставленный photo/video обрабатывается
существующим decoder с отдельными ad labels; точный post_id/permalink — shared
resolver, ad_id не используется как media ID. В историю попадает только понятный
рекламный контекст. Разные объявления разделяют пакет. Для проверенной рекламы
доступен title «Рилс ВДП Рождество»; full post/video текущим доступом не доказан.
Правила тематики и эскалации восстановлены после уточнения владельца: третий
пункт относился к формулировке, а не сотрудничеству. Общее правило промпта требует
заглавную букву в начале предложения и содержательное продолжение без пустого
«с радостью подскажу». Это инструкция модели, без изменения регистра/ссылок кодом.
| reaction / read / delivery / deletion | служебное событие, без ответа |

Fallback не утверждает успешную передачу менеджеру при ошибке Telegram и не
увеличивает лимит. Takeover проверяется под lock, после username lookup и перед
ответом, в том числе при технической ошибке. Расшифровка голосовых исключена.
Этот маршрут обеспечивает отказ без выдуманного содержания, не гарантирует
доступ к исчезнувшей/закрытой истории или понимание всех возможных файлов.

```
  → _process_non_text_safely(sender_id, text, metadata):
      manager takeover gate
      _get_lock(sender_id)  # per-user lock
      instagram.get_username(sender_id)  # best-effort, кеш
      escalation_count < 3:
        → TelegramNotifier.notify_manager(
            context="Тип: summary\nТекст клиента: ...\nБот не видит вложение")
        → escalation_count++
        → client ack: "Не вижу вложение/пост/историю, передала менеджеру"
      escalation_count >= 3:
        → client ack: "Ваш запрос уже передан менеджеру, ожидайте"
      save_session()  # история + escalation_count
      instagram.send_message(client_reply)
  **LLM не вызывается.**
```

### Ответ с вопросом на собственную историю (08.10.2026)

При `STORY_MEDIA_ENABLED=true` текстовый story reply передаёт точный `story.id`
в AI-поток. `src/services/story_media.py` подтверждает ID среди активных историй
нашего Instagram-аккаунта, получает полный файл по Graph API и скачивает его
отдельным клиентом с разрешённых Meta CDN без передачи токена и редиректов.
Webhook URL не используется как подмена полного видео.

VIDEO: `decode_story_media.ps1` извлекает ровно 10 равномерных NearestFrame
от начала до последнего доступного кадра, в исходном размере, без обработки
звука и OCR. IMAGE: декодер проверяет изображение и передаёт его целиком.
Очень короткое видео может иметь одинаковые ближайшие кадры.
Последний HumanMessage содержит исходный вопрос и все изображения
с `detail=original`; `get_vision_llm()` использует `DEEPSEEK_VISION_MODEL`
(по умолчанию `deepseek-flash`), один вызов без автоматических повторов.
Каталог, FAQ, история и существующие правила ответа/эскалации сохраняются.

Отдельная блокировка обработки клиента сохраняет порядок вопросов; подготовка
медиа не держит блокировку сессии, чтобы менеджер мог установить паузу.
Ожидающий перехват отмечается сразу при приёме manager-event и проверяется
до AI, после генерации и перед отправкой частей. Очередь пропускает ожидающий
перехват и удаляет старые автоматические ответы при активном менеджере.
В истории остаются вопрос и пометка ID/типа истории, без URL и base64.
Ошибки медиа/vision дают честный вопрос о названии тура через общую доставку.

Лимиты: файл 25 MiB, видео 90 секунд, габарит 4096 пикселей,
изображения суммарно 24 MiB, подготовка 90 секунд, декодер 60 секунд,
2 параллельные подготовки. Временные файлы удаляются после закрытия декодера,
включая ошибки и отмену. Флаг по умолчанию выключен. Голосовые, произвольные
входящие видео и Reels не входят в этот этап.
Обычные фото и shared posts/Reels добавлены отдельными расширениями ниже;
здесь описан story flow.
Windows запускается одним Uvicorn worker без `--reload`: нужен Proactor loop
для асинхронного дочернего процесса. На других платформах доступен текстовый
путь, а попытка включить story decoder даёт безопасный fallback.

### Обычные изображения (08.10.2026)

`attachments[].type=story_mention` с 11.10.2026 направляется в отдельный
`user_silent_handoff` до reaction/voice/media веток. Весь исходный event молча
передаётся менеджеру; отдельные соседние сообщения не поглощаются. Действуют
MID dedup, manager takeover и лимит3. Нет AI, скачивания или ответа/очереди
клиенту при успехе, ошибке и лимите. В истории — только понятная пометка входящего
упоминания. Прежний vision-путь упоминаний заменён по просьбе владельца.
Обычный ответ на историю продолжает использовать точный ID и фото/10 video frames.
Приглашение соавтора из проверенного события имело лишь `unsupported_type`;
отдельный признак не доступен, поэтому общий тип не переведён в silent режим.

`IMAGE_MEDIA_ENABLED=true` включает анализ JPEG/PNG, присланных как
`attachments[].type=image` или `video` с `payload.url`. Список URL хранится только в
событии фоновой обработки; в логах, истории и уведомлениях менеджеру его нет.
`prepare_images()` скачивает изображения с разрешённых Meta CDN без токена,
проверяет настоящий формат/декодируемость и габариты, удаляет временные файлы.
Исходные байты JPEG/PNG уходят в DeepSeek без изменения размера/сжатия.

Подпись и до 10 визуальных вложений одного сообщения или объединённого webhook попадают
в один HumanMessage с `detail=original`, одним vision-вызовом. Все подписи
внутри webhook соединяются по порядку, все MID остаются в дедупликации.
Повторные отдельные MID исключаются до объединения, чтобы повтор старого
фото не скрывал новые фото/текст того же payload. Разные клиенты и story events
не объединяются. Фото и VIDEO объединяются; фото+audio/ig_post не считаются набором фото.

Без подписи передаётся `[Изображение без подписи]`: бот кратко распознаёт
содержание/тур и уточняет вопрос. Этот вызов не отмечается как полученный текст
для соседнего post/Reel. Фото/видео и следующий вопрос из разных POST в текущем
5-second окне объединяются; поздний вопрос получает историю предыдущего ответа. При недоступном/неверном файле бот просит повторить
фото JPEG/PNG или написать вопрос, без подмены распознавания текстовым AI.
В БД сохраняются реальные подписи либо пометка без подписи и число изображений.
Каталог, FAQ, guard, перехват менеджером и очередь совпадают со story flow.
Размеры, таймаут и concurrency общие; набор ограничен 24 MiB суммарно.

Флаг изображений по умолчанию выключен и независим от story-флага. IMAGE-ответ
на own story идёт через story ID; thumbnail рядом с VIDEO story не заменяет видео.
Истёкшие/недоступные URL сохраняют безопасный fallback; точный incoming mention
URL не подменяется похожей собственной историей. Обычный image не становится
VIDEO по ошибке. GIF определяется также по magic GIF87a/GIF89a и не отправляется
AI; если остался только вопрос, используется text AI, без вопроса — тишина.
На весь набор действуют 10 исходных вложений, 100 output images и 24 MiB.

### Пересланные публикации и Reels (08.10.2026)

`SHARED_MEDIA_ENABLED=true` включает обработку `ig_post`/`share`/`ig_reel`. Канал сохраняет
media ID/URL до resolver и объединяет вопрос, источники и MID одного webhook.
Точный Graph media object даёт `media_type`, полный `media_url`, подпись и children.
Permalink можно сопоставить с публикациями нашего аккаунта; если указаны и ID,
и permalink, должны совпадать оба. HTML страницы и thumbnail не заменяют оригинал.

IMAGE передаётся целиком, VIDEO/Reels — ровно 10 original кадров каждого видео.
CAROUSEL_ALBUM анализируется полностью, по порядку: до 10 элементов/100 кадров,
общий лимит изображений 24 MiB. Неполная/пагинированная карусель даёт fallback.
Кадры и подписи имеют одинаковые номера публикаций/элементов; подпись считается
данными. Всё содержимое и вопрос идут одним vision-вызовом, без звука/OCR/повторов.
Без вопроса бот кратко распознаёт содержание и уточняет интерес клиента.

Длительность видео берётся из MP4 video-track mdhd (hdlr=vide), затем ограничивает
Windows OriginalDuration. Это исправляет последний кадр Reels, когда аудио длиннее
видеодорожки; см. `runtime/windows-reel-last-frame.md`. Cleanup/allowlist/guards/
takeover/очередь и text-only история переиспользуют общий поток.

Если Meta не даёт точное полное медиа, бот просит оригинал или сведения текстом.
Универсальная доступность чужих/приватных постов не гарантируется. Флаг по умолчанию
выключен. Локальное QA: полный pytest 403 PASS, Ruff PASS; собственный реальный
Reels → 10 кадров 0.000–8.500 с без AI. По запросу «деплой» 08.10.2026 все три
media-флага включены в production; server pytest 401 PASS/2 JPEG-artifact skips,
Ruff PASS, native VIDEO/IMAGE/VIDEO → 21 изображение, local/public health 200/ok.
Live native Reels успешно прошёл подготовку, vision и отправку после micro fix ниже;
live own story/фото/carousel ещё не проверены, их интеграционный AI проверен mock.
Первый live Reels пришёл как `ig_reel` и выявил отсутствие этого типа в allowlist.
Micro patch включён после 408 local PASS/406 server PASS/2 JPEG skips, Ruff PASS;
12 SHA и health verified. Повторный payload подтвердил ig_reel/reel_video_id:
полное видео → 10 кадров → один vision (32617 input/259 output) → Instagram
message.sent за 14.4 с. Полный URL/raw payload/base64 не сохранялись в истории.

## Ключевые компоненты

### main.py — FastAPI сервер
- `/health` — healthcheck
- `GET /webhook/instagram` — верификация Webhook (hub.challenge)
- `POST /webhook/instagram` — приём, dedup и dispatch по типу/тексту/медиа; manager → takeover, silent handoff — отдельная ветка
- `/webhook/instagram/last_seen` — диагностика, приходили ли POST от Meta
- `POST /api/admin/reset-takeover/{client_id}` — отдельная административная запись, защищена admin token; не шаг переноса или нейтральной диагностики
- `GET /api/admin/inbound-recovery` — защищённый статус восстановления
- `lifespan` — асинхронная загрузка FAQ (ChromaDB) и туров (DOCX) при старте
- `_process_safely` — обёртка с логированием, запускается в фоне (LLM-путь)
- `_process_non_text_safely` — безопасный fallback для оставшегося non-text; поддержанные медиа и silent handoff маршрутизируются отдельно
- `process_with_ai` — основной пайплайн с DeepSeek

### config.py — Pydantic Settings
Все переменные из `.env`, типизированы. Помимо API-ключей хранит лимиты защиты:
`max_message_length`, `max_messages_per_minute`, `manager_takeover_ttl_minutes`.

### src/ai/prompts.py — Системный промпт
Единый промпт, собирается в `build_full_prompt()`:
- `_BASE_RULES` — роль (Сандита, Минск), правила общения, фильтр дат, контакты
- `_SECURITY_RULES` — защита: запрет смены роли, раскрытия промпта, «я ИИ»
- `_TOURS_HEADER` + tours_text — база туров из DOCX
- `_FAQ_HEADER` + faq_context — результаты ChromaDB-поиска
- `_ACTION_INSTRUCTIONS` — бронирование по ссылке и обработка отзывов
- `_ESCALATION_RULES` / `_ESCALATION_LIMIT_REACHED` — Telegram-эскалация до 3 раз
- `_RESPONSE_RULES` — аргументы одного `prepare_response`: `reply` и `manager`; `_AD_DECISION_RULES`
  задаёт только смысловые условия молчаливой передачи рекламы.

### src/services/guard.py — Детерминированная защита
- `check_input()` — пустые/слишком длинные сообщения и prompt-injection до LLM
- `is_rate_limited()` — per-sender лимит сообщений в минуту
- `check_output()` — fallback, если модель раскрывает служебную природу или вендора

### src/services/llm.py — Обёртка DeepSeek API
- `get_llm()` / `get_vision_llm()` — общий strict tool transport через beta endpoint,
  temperature=0.1, thinking disabled, max_retries=0; max_tokens=2048 через extra_body.
- Один forced `prepare_response`, без response_format. Vision сохраняет original
  images. `_ResponseModel` сохраняет raw provider message до SDK-конвертации,
  которая иначе теряет duplicate JSON keys. `response_arguments()` проверяет
  envelope; исходные arguments проходят прежний строгий reply/manager validator.
- Tool только подготавливает результат; отправки и подтверждения выполняет
  приложение. В истории остаётся видимый текст, без tool-call/result сообщений.
  N31: tool transport включён только для numeric allowlist `DEEPSEEK_TOOL_CLIENT_IDS`.
  Пустой список оставляет JSON всем; некорректный запрещает запуск. Выбор на
  клиента фиксируется до prompt/factory/retry/parser. Остальные получают точные
  installed JSON prompt и `get_legacy_llm/get_legacy_vision_llm`; recovery scope
  не влияет на этот выбор. Canary выложен только @_shelter_0; manifest обновлён.
  N32: отдельный `DEEPSEEK_TOOL_SCOPE=all` включает tools для всех клиентов,
  оставляя allowlist для отката; default `allowlist`. Глобальный scope выложен,
  режим recovery на этапе N32 был тестовым. Последующую активацию `all`
  2 ноября фиксирует `runtime/recovery-all-activation.md`; текущее датированное
  описание см. в разделе recovery ниже.

### src/services/tour_loader.py — Загрузка DOCX
- `load_tours()` — читает все `.docx` из `tours/`, собирает в единый текст
- `get_tours_text()` — возвращает кешированный текст

### src/db/faq_db.py — RAG FAQ через ChromaDB
- `load_faq_to_chroma()` — загружает проверенные FAQ из `data/faq/` в пустой индекс ChromaDB; заполненный индекс автоматически не обновляет
- `search_faq(text)` — векторный поиск, возвращает top-3 документа. При отсутствии TXT-источников загрузка и поиск отключены до обращения к Chroma, поэтому старый индекс не используется. Стартовые неподтверждённые FAQ удалены.

### src/db/sessions.py — SQLite сессии
- `get_session()` / `save_session()` — хранение истории диалога
- `read_row()` / `write_row()` — транзакционная запись состояния с revision и защитой от конфликтов; менеджерские задачи и исходящие подтверждения находятся в соседних SQLite-модулях

### src/services/tour_sync.py — синхронизация каталога Google Drive
- Проверка источников, last-good snapshot и обновление каталога с отдельными настройками `TOUR_SYNC_*`.
- `GOOGLE_DRIVE_CREDENTIALS_FILE` указывает на приватный файл доступа; заявки и их статусы хранятся в SQLite, отсутствующего `google_sheets.py` в runtime нет.

### src/services/telegram_notify.py — Telegram-уведомления
- `notify_manager(sender_id, instagram_handle, context, ...)` — отправка контекстной карточки клиента менеджеру без истории переписки
- Подтверждение клиенту формирует приложение по факту Telegram HTTP200/JSON `ok=true` минимум для одного настроенного получателя; частичный сбой логируется. При лимите новое уведомление не отправляется, при ошибке подтверждение передачи отсутствует. Модель не обещает передачу или обратный звонок; финальная защита сохраняет полезный текст, вопросы, ссылки и контакты. Проверки и границы: `runtime/telegram-handoff-receipt.md`.
- `_build_notification_text()` — формат: 🚨 Новая эскалация, 👤 @handle, 🕐 таймстемп, 📋 суть, контакты (опционально)
- `deliver_task_operations(...)` — доставка операций менеджерских задач с отдельным учётом результата

### src/channels/instagram.py — Instagram Direct
- `verify_signature()` — проверка `X-Hub-Signature-256`; без `INSTAGRAM_APP_SECRET`
  разрешено только локально
- `receive_message()` — разделяет сообщения клиента на `kind="user"` (текст),
  `kind="user_non_text"` (вложение/пост/story reply/referral) и `kind="manager"` (echo менеджера)
- `_extract_non_text_metadata()` — детектирует `attachments`, `reply_to`, `referral`
  и возвращает структуру с `types`, `summary`, `has_text`, `text`, `raw_keys`
- Временная диагностика `instagram.story_reply.context` фиксирует `mid`, валидный
  числовой `story_id` (ASCII, до 32 символов), `story_id_present`, `story_id_valid`
  и `has_story_url` для `reply_to.story`, включая реакции и события без текста.
  URL истории, исходный payload и текст сообщения не пишутся в эту запись.
  Содержательные ответы дополнительно сохраняют безопасное `story={id}`
  для опционального media flow; ID с неверным форматом становится None.
- `send_message()` — отправка через Graph API; распознаёт rate-limit Meta
  (`error.code` в теле ответа даже при HTTP 200: `4/17/32/613/80002`) и кидает
  `InstagramRateLimitError` с `retry_after_seconds` из заголовка
  `X-Business-Use-Case-Usage`, если он есть; при успехе сохраняет `message_id`
  для echo-фильтра
- `_sent_mids` — `_MidSet`, множество с FIFO-эвикцией по размеру (не обычный
  `set`, у которого `.pop()` удаляет произвольный элемент)
- `get_username()` — best-effort username/name с in-memory кешем

Провал `send_message()` во всех трёх местах вызова в `main.py`
(`process_with_ai`, `_process_non_text_safely`, `_process_safely`) теперь
логируется структурированным `logger.error("instagram.message.lost", ...,
reason="rate_limited"|"other")` — раньше сообщение клиенту терялось молча
под обычным `logger.exception`.

## Единый ответ LLM

Все модельные маршруты возвращают ровно `{reply:string, manager:null|object}`.
Объект manager содержит только context (1–450 символов), type
(консультация/контакт/отзыв), name (до100 символов, пустая строка если неизвестно).
Обычный ответ имеет manager=null; ответ с эскалацией — непустые reply и manager;
молчаливая передача неясной рекламы — пустой reply и manager. Пустой reply для
обычных обращений недопустим. Номер извлекается из текущего ввода, включая
однозначный явный номер внутри фразы; модель телефон не возвращает.

Единый строгий валидатор проверяет ключи/типы/дубликаты и служебные маркеры.
Один повтор формата/пустого ответа разрешён всем маршрутам, максимум2вызова.
После второй ошибки — техническая эскалация; ADS молчит, обычный запрос получает
фиксированный честный ответ. Провайдер/length/oversize/non-string терминальны.
В клиентский канал и assistant history попадает только доставленный reply,
без JSON и manager. Старые маркеры очищаются из prompt history; в новом reply
маркеры отвергаются. Бронирование остаётся ссылкой на сайт, без отдельного action.
N28 выложен и проверен; состояние production фиксирует runtime-manifest.json.

## Дедупликация

Телефонные contact/template карточки нормализуются в текст только по узкой
структуре контакта. Incoming `payload.generic` поддерживается отдельно от flat
outgoing template. После подписи и регистрации MID webhook собирает события
клиента до пяти секунд тишины после последнего нового MID и сразу возвращает
Meta 200. Тексты объединяются по порядку; пустой generic рядом с содержательным
текстом игнорируется без отдельного AI/Telegram и без извлечения номера.
Телефонная карточка с содержимым сохраняет строгую нормализацию; одинаковые
phone text/card объединяются только в текущем пакете со всеми MID. Кеша старых
телефонов и подавления fallback по AI timestamp больше нет. Неизвестные непустые
вложения сохраняются. Истории с разными ID остаются отдельными запросами;
фото/публикации сохраняют источники и подписи. Новое сообщение во время AI
открывает новое окно; пакеты одного клиента обрабатываются последовательно.
Recovery сохраняет received_at в SQLite; цепочка соседних сообщений с паузами
не более5с образует пакет. Разрыв>5с разделяет пакеты даже после задержки worker.
Manager echo обрабатывается сразу, отменяет ожидающий пакет; error fallback
также проверяет takeover. Единственная задержка находится перед dispatch.

Manager marker extraction допускает незакрытый блок до EOF, cleanup удаляет
также повреждённый header; служебное содержимое не входит в visible ответ и новые
assistant записи. Старые assistant blocks очищаются только в prompt-copy.
Notifier использует подтверждённый input phone при отсутствии model phone field;
контакт эскалируется даже без AI marker, а phone-only ack выбирается по факту
success/error/limit notifier и не содержит повторных обещаний модели;
прежние лимиты эскалаций и manager takeover применяются.
При current phone номер/tag строятся кодом; context — короткая модельная выжимка
с проверкой либо bounded fallback (N6). AI old phone в контексте/имени и prior mixed
contact не переопределяют новый номер; current question приоритетен.
Known formatted phone spans исключаются независимо от соседнего budget/date,
ISO даты и суммы без телефона остаются в query. Диагностика источника — boolean. См.
`runtime/instagram-phone-card-marker.md` и spec N1/N2/N1b.

- `_processed_mids: _MidSet` — хранит message_id до 10 000 записей
- При превышении — удаляет самые старые записи через `pop_oldest()`
- Per-user lock (`asyncio.Lock`) предотвращает гонки
- `_sent_mids` в InstagramChannel помогает отличать echo собственных сообщений бота
- `manager_last_at` в SQLite-сессии включает паузу бота после ответа менеджера

## Тесты

- `pyproject.toml`: `asyncio_mode = "auto"`
- `conftest.py`: добавляет корень проекта в `sys.path`, объявляет Playwright fixtures
- Текущий набор определяется командой `python -m pytest tests/ --collect-only -q`; числа в runtime относятся к своим датированным проверкам
- Каноничная команда: `pytest tests/ -q`

## Ключевые файлы

Это навигационный обзор, не автоматически сгенерированное дерево.

| Подсистема | Файлы |
| --- | --- |
| Приём и dispatch | `src/main.py`, `src/channels/instagram.py` |
| Настройки и промпты | `src/config.py`, `src/ai/prompts.py` |
| Сессии, очередь и receipts | `src/db/sessions.py`, `inbound.py`, `pending_messages.py`, `manager_tasks.py` в `src/db/` |
| Recovery/reconcile | `src/services/inbound_recovery.py` |
| Модель и handoff | `src/services/llm.py`, `handoff_review.py`, `model_failure.py` в `src/services/` |
| Каталог и FAQ | `src/services/tour_loader.py`, `src/services/tour_sync.py`, `src/db/faq_db.py` |
| Медиа и голос | `src/services/story_media.py`, `ad_media.py`, `voice_media.py`, `gigaam_worker.py` в `src/services/` |
| Уведомления и диагностика | `src/services/telegram_notify.py`, `diagnostic_trace.py`, `llm_response_log.py`, `meta_diagnostics.py` в `src/services/` |

## Связанные документы

Голосовые (GigaAM): audio attachments при `VOICE_MEDIA_ENABLED` сохраняются в
ordered voice/text parts; collector с5с тишины объединяет их с supported visual parts
без потери MID. Один отдельный resident Python worker принимает локальные файлы
через private JSON-lines pipe, декодирует mono16kfloat32 и распознаёт GigaAM на CPU.
Модель/зависимости изолированы от runtime бота, download/STT очередь и размеры
ограничены. История хранит расшифровку, без audio URL. Расшифрованный вопрос и
изображения поступают в один существующий DeepSeek запрос. STT error/empty/limits
→ немедленное краткое уведомление менеджеру и retry/text ответ, без DeepSeek
для обычных сообщений. Для ADS безопасный текст и статус сбоя всё равно идут
в DeepSeek: решение `handoff` вызывает менеджера молча;
manager takeover остаётся приоритетным. Прямое видео/истории без расшифровки звука.
Подробности границ и проверок: `runtime/gigaam-voice-integration.md`.

- [README](../README.md) — вход в актуальную документацию, состояние локальной работы и выкладки
- `docs/DEPLOY.md` — деплой на сервер (Windows + Cloudflare Tunnel)
- `docs/SETUP.md` — локальный запуск

## Durable inbound recovery — defaults и состояние выкладки

В `sessions.db` добавлены журнал событий, задания, исходящие intent/receipt и
контрольные точки API. `src/db/inbound.py` хранит транзакции, версии и аренды;
`src/services/inbound_recovery.py` запускает прежний dispatch с отложенной
записью session/send/notify. Внешние вызовы не выполняются внутри SQLite-транзакций.
Validated draft записывается до отправки; история assistant и счётчик эскалаций
меняются после receipt. Неопределённая отправка блокируется для проверки,
а не повторяется автоматически. Старые pending совместимы через receipt bridge.

Группировка 5 с; watchdog 60 с; два технических повтора 120/480 с; один
семантический пересмотр 120 с. Scanner Conversations API стартует вместе
с функцией и работает раз в 120 с, сохраняет cursor/baseline/backoff и явно
отмечает неполноту. Обычная сверка не вызывает модель. API-only неполный
контекст использует единый reply/manager JSON без фиктивного ADS.

Defaults recovery/reconcile в Settings — false. Это не описание текущих серверных флагов: по [журналу активации](../runtime/recovery-all-activation.md) общий scope включён 2 ноября; по [quiet-window release](../runtime/inbound-quiet-window.md) 4 ноября обновлены два исходника при сохранении scope all. Для нового deployment нужна свежая серверная сверка. Полный контракт — `.kiro/specs/inbound-recovery/`, исторические ограничения первой версии — `runtime/instagram-inbound-recovery.md`.

Первый выпуск добавляет единый allowlist/all scope на ingress/SQLite claims/
scanner/sends. Остальные клиенты остаются legacy, включая pending worker.
Тестовая baseline сохраняется отдельно от первой общей; расширение scope
не отвечает переписке, накопленной до включения соответствующей области.
API permalink идёт в прежний shared resolver; visual-only mixed batch
использует прежний composite media flow без запуска STT. Недоступные через
API вложения — неполный контекст, а не фиктивная реклама.

