# Рабочее окружение

N6 contact summary: test_engine.py проверяет короткий модельный Контекст с туром,
вопросом и визой, историю→ответ→телефон, source/phone isolation, current question
priority, missing/invalid/overlong summary и краткий fallback без full answer.
No-caption/unavailable не возвращаются к чужому туру; history unchanged,
один прежний AI-вызов. Реальную проверку делает новым сообщением владелец;
не отправлять вручную уведомления/не сбрасывать сессию без нового разрешения.

Story reaction regression S7: tests/test_inbound_batch.py воспроизводит emoji →
plain question через25с без ожидания реальных секунд (monotonic mock), MID retry,
TTL120с, cap, isolation, new-story snapshots/merge, media/phone/manager precedence.
Live проверка: реакция на доступную собственную историю, затем отдельный вопрос
в течение двух минут. Нужна новая реакция после рестарта; кэш одноразовый и только
в памяти. Не сбрасывать session/лимиты для теста без отдельного разрешения.

> Навигация обновлена 4 ноября 2026. Датированные N/V-секции ниже — история отдельных изменений; текущее состояние выкладки см. в [README](../README.md).

## Локально

Установка и отдельные команды Mac/Windows — в [SETUP](SETUP.md).
Рабочая Windows `.venv` не переносится на Mac как исполняемое окружение.

Основные offline-проверки из нужной `.venv`:

```bash
python -m pytest tests/ -q
python -m ruff check src tests
```

`black src tests` изменяет файлы; для отдельной проверки форматирования используется `python -m black --check src tests`. Массовое переформатирование не является шагом миграции.

Запуск с рабочими ключами может включить фоновые отправки. Сначала подготовить тестовые подключения и копию данных; локальный сервер привязывать к `127.0.0.1`.
Для проверки историй на Windows задайте `STORY_MEDIA_ENABLED=true`,
для обычных JPEG/PNG и прямых видео — `IMAGE_MEDIA_ENABLED=true`, для публикаций/Reels —
`SHARED_MEDIA_ENABLED=true` (все флаги независимы и по умолчанию выключены).
Запускайте Uvicorn **без `--reload` и без нескольких workers**:
`python -m uvicorn src.main:app --host 127.0.0.1 --port 8000`.
Story mention и `unsupported_type` имеют отдельный silent-handoff маршрут; включение image-флага не превращает их в обычный image-запрос.
Windows-декодеру нужен Proactor event loop; reload/multi-worker запуск
установленной версии Uvicorn выбирает Selector и не поддерживает
`asyncio.create_subprocess_exec`. Новые зависимости для декодера не нужны.

Точный состав тестов определять по `python -m pytest tests/ --collect-only -q`.
Профильные команды приведены ниже; численные результаты в runtime — датированное evidence.

`pyproject.toml` задаёт `asyncio_mode = "auto"`. `conftest.py` добавляет корень
проекта в `sys.path` и объявляет Playwright fixtures `browser` / `page`.

## Переменные и секреты

Рабочие секреты лежат в `.env` и настроенных файлах `credentials/`; они игнорируются Git. Источники настроек — `src/config.py` и `.env.example`, подробнее [ENV-SETUP](ENV-SETUP.md). Не коммитить секреты и не копировать их в документацию.

Обязательные поля зависят от включённых интеграций. Google Drive используется для синхронизации туров; старые `GOOGLE_*SHEET*` переменные не являются текущим runtime.

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

Перед отдельным коммитом проверить `git diff`, новые файлы, удаления и секреты; добавлять только явно выбранные пути. Коммит и push — по запросу владельца. Они не являются deployment. Последние серверные пакеты устанавливались напрямую, поэтому сначала сверить [статус](../README.md) и [процедуру](DEPLOY.md).

## Сервер (Windows)

Быстрые команды и актуальные адреса — в `docs/DEPLOY.md`.

Проверка сервиса:

```powershell
# SSH
ssh sundita-office "chcp 65001 >nul & curl http://127.0.0.1:8000/health"
ssh sundita-office "chcp 65001 >nul & curl http://127.0.0.1:8000/webhook/instagram/last_seen"

# Health через домен
curl https://sundita.online/health
curl https://sundita.online/webhook/instagram/last_seen
```



## Проверки маршрутов

Для регрессий использовать pytest и локальные mock/ASGI fixtures. Неподписанные POST в production webhook не являются безопасной smoke-проверкой: они расходятся с проверкой подписи и могут запустить реальные операции. Live-сценарии — только с отдельным разрешением и контролем внешних действий.

Phone/template/batch regression: `pytest tests/test_inbound_batch.py tests/test_phone_contacts.py tests/test_engine.py -q`.
Voice regression: `pytest tests/test_voice_messages.py tests/test_voice_media.py -q`.
Флаг `VOICE_MEDIA_ENABLED=false` по умолчанию сохраняет прежнюю обработку audio.
Для включения нужны `VOICE_PYTHON_EXECUTABLE` (отдельное Python окружение) и
`VOICE_MODEL_DIR` (локальные SHA-verified GigaAM ONNX files). Устанавливать
`requirements-gigaam.txt` только в это окружение, не в окружение бота. Worker
запускается лениво, получает локальные файлы через pipe, shutdown отменяет и
ожидает только принадлежащий приложению процесс. При STT error клиенту предложить
повторить запись/написать текстом, менеджеру немедленно отправить краткий контекст.
Live voice проверка — новое голосовое владельца после deployment authorization;
не replay webhook и не делать manual paid/model/client/manager calls для QA.
Записи/тексты/Signed URLs не печатать в логах. Staged real native proof и процедура
backup/rollout/rollback описаны в `runtime/gigaam-voice-integration.md`.
Окно 5 секунд проверяется async ASGI-запросами с управляемым таймером и одним
настоящим ожиданием; dispatcher tests отдельно подменяют только ожидание.
Story mention/ad/business regression: `pytest tests/test_inbound_business_context.py tests/test_inbound_batch.py tests/test_story_media.py -q`.
Проверяются silent outcome/limit/takeover, оба порядка самостоятельного соседнего
вопроса, приоритет над reaction/audio/media, referral через voice/merge, раздельные
ad media labels и общие правила формулировки без изменения business policy.
Unsupported/coauthor не смешиваются.
Live проверка требует нового упоминания владельцем; URL/payload не писать в логи.
Смотреть только `instagram.template.context` (payload_keys/generic_keys/type/count,
recognized_phone), `instagram.batch.ready` (received/dispatched),
`instagram.batch.empty_template_ignored` и limit/takeover/send события.
Не выводить raw payload, телефон или текст истории. Live-проверка проводится
новой отправкой владельца; не replay webhook и не сбрасывать production лимит/
takeover для тестирования без авторизации. Если Windows temp недоступен, передать
pytest новый `--basetemp` в рабочей папке. Все tests изолируют SQLite в conftest.
Conftest блокирует реальные httpx HTTP transports: использовать MockTransport/
ASGITransport или явные mocks. Новые маршруты нужно подменять в dispatcher fixture,
чтобы отсутствие mock не превращало pytest в реальные сообщения менеджерам.

Реклама: `ADS_MEDIA_ENABLED`, `INSTAGRAM_ADS_ACCOUNT_ID`, `INSTAGRAM_ADS_TOKEN_FILE`.
Для дополнительных согласованных кабинетов: `INSTAGRAM_ADS_ACCOUNT_IDS` (CSV).
Список объединяется с прежним одиночным ID, максимум10 уникальных числовых ID;
ошибочный список отклоняется до сети. Startup health проверяет каждый кабинет;
ad.account_id проверяется по явному списку до чтения creative. Добавления ID в
настройки недостаточно: системный пользователь должен иметь ANALYZE в Meta.
Ошибка100/33 сама по себе не доказывает другой кабинет или удаление объявления;
проверять точный ID после grant, при необходимости exact ad.id фильтр на ads edge.
Файл содержит только отдельный System User ads_read token, находится вне Git в
credentials/ с доступом только служебного пользователя и администраторов. PAGE
messaging credential не заменять. Marketing v26.0 exact ad/account/creative →
effective IG media (source fallback только с тем же exact permalink) → PAGE
v25.0 media_url/caption → штатные10originalframes/один общий vision запрос.
Источник с другим permalink, dynamic creative без доказанного варианта, preview
вместо видео, expired/missing credential не передаются модели как исходный материал.
Каждый допустимый ADS запрос поступает в DeepSeek вместе с безопасным текстом,
историей и явным статусом недоступного материала. Единый `prepare_response`
возвращает `reply/manager`: модель решает понятность; непустой reply идёт в ответ,
пустой reply с manager — краткая выжимка менеджеру без сообщения клиенту.
Пустые/пробельные arguments без обрезания получают один повтор с теми же
сообщениями и кадрами; ошибка формата — один повтор с доверенным напоминанием.
Повторная ошибка, терминальный неверный тип/размер/обрыв и ошибка модели дают
молчаливую передачу. Локального словарного гейта нет.
Пауза менеджера, защита входа и частотные ограничения остаются приоритетными;
неподдерживаемые файлы/товары требуют менеджера после вызова модели.
QA маршрута: `pytest tests/test_ad_model_decision.py -q`; mocks проверяют
маршрутизацию и молчание, а не качество понимания реального DeepSeek.
Восстановление после пустого ответа: `pytest tests/test_ad_empty_response_retry.py -q`.
Перед повтором и обработкой результата проверяется перехват менеджером; история
и уведомления формируются только по окончательному результату. Максимум два
`ainvoke`; SDK-повторы выключены для текста и vision.

Исходные аргументы DeepSeek записываются до прикладного разбора в отдельный локальный
`logs/deepseek-responses.jsonl`: текст, причина проверки, UTC-время, модель,
псевдоним клиента, токены, UUID обработки и номер попытки. Пустые строки и
невалидный JSON сохраняются; для некорректного tool envelope сохраняется исходное
message, включая конфликтующий content. UUID одинаков у обеих попыток. В `bot.log` остаются
только безопасные метаданные/UUID, без содержимого ответа. Prompt, изображения,
произвольные metadata и исключения поставщика не сохраняются в новом журнале.
Известные credentials, Bearer/ключи, data URLs и подписанные медийные ссылки
маскируются; текст ограничен64тыс.символов с явным признаком обрезки. Журнал всё
равно содержит тексты ответов клиентам и доступен по файловым правам сервера:
POSIX новые файлы0600, Windows наследует ACL каталога logs. Не публиковать его.
Ротация:5MiB и7архивов, примерно40MiB; это ограничение объёма, а не7дней хранения.
`DEEPSEEK_RESPONSE_LOG_ENABLED=false` отключает запись (по умолчанию true).
Ошибки инициализации/маскирования/записи/ротации дают только безопасный
`llm.response_log.failed` и не меняют ответ бота. Проверки:
`pytest tests/test_llm_response_log.py -q`; файлы журнала изолируются в tmp_path.
Публичный /health при включённой функции показывает только ads_media.enabled/
ready/reason; scope/account проверяются при запуске без исходников в логах.
Токен можно заменить в приватном файле без смены messaging credentials; срок
и отзыв доступа Meta нужно проверять фактически, а не обещать «навсегда».
QA: `pytest tests/test_ad_media.py -q`, полный pytest/Ruff, native server proof
без paid AI/client sends. Никогда не печатать токен, signed URL или raw API error.

```powershell
ssh sundita-office "chcp 65001 >nul & type C:\travel-agent-bot\nohup.out 2>nul"
```
## Единый результат модели (N28 contract, N30 tool transport)

Текст, реклама, расшифрованные голосовые и vision используют один контракт: `reply` плюс nullable `manager`
с context/type/name. Номера и подтверждения доставки добавляет программа.
Готовые программные fallback-ответы не проходят через модельный JSON-парсер.
Получаем его единственным strict `prepare_response` через beta API, forced tool,
thinking.disabled. JSON Output fallback отсутствует. Не добавлять обратную
совместимость с обычным content/marker-ответами. `_ResponseModel` сохраняет
исходное provider message в additional_kwargs.raw_tool_message до SDK parsing;
не восстанавливать arguments из parsed tool_calls (дубли ключей уже потеряны).
В тестах используйте явные `model_response/tool_response` из tests.model_responses;
ошибочные arguments не исправляются helper-ом. `arguments_of/set_arguments`
нужны для явного чтения/повреждения raw fixture, content остаётся пустым.
Номера, лимиты, receipts и recovery checkpoints принадлежат программе.

N31 canary: `DEEPSEEK_TOOL_CLIENT_IDS` содержит только проверенные числовые
Instagram IDs; по умолчанию пуст и не зависит от inbound recovery allowlist.
Остальные клиенты используют installed JSON lane. `use_tools` фиксируется
на запрос и повтор, без глобальных переключений. Common business tests явно
подменяют gate в conftest, чтобы упражнять N30; `test_tool_canary.py` возвращает
настоящий gate и проверяет default-off/invalid/mixed clients/застывший retry.
12 golden hashes для legacy prompt+retry получены из installed baseline.
`test_tool_canary_release.py` проверяет inverse rollback без восстановления БД.
N32: `DEEPSEEK_TOOL_SCOPE=all` включает tool lane для всех клиентов, в том числе
новых; default `allowlist`. Это не расширяет recovery. Rollout controller
`--scope all` проверяет исходную здоровую canary и добавляет только этот envkey;
откат возвращает прежнюю конфигурацию без замены актуальной SQLite.

Проверки: `pytest tests/test_model_tools.py tests/test_tool_handler.py
tests/test_unified_model_response.py tests/test_engine.py
tests/test_handoff_receipt.py tests/test_voice_messages.py -q`, затем полный
pytest и Ruff. Native Windows-декодер требует обычного окружения Windows вне
ограничений sandbox; проверки не ослаблять и медиа-тесты не пропускать.
Платные API-прогоны и production rollout выполняются только с разрешением на
соответствующие действия. Не считать зелёные mocks доказательством реального
ответа провайдера. При смене формата действующие старые trial-скрипты требуют
обновления и не должны случайно использоваться для выкладки новой версии.

## Восстановление входящих (локальный candidate)

`INBOUND_RECOVERY_ENABLED` и `INSTAGRAM_RECONCILE_ENABLED` выключены по
умолчанию. Для изолированных проверок: `pytest tests/test_inbound_recovery.py
tests/test_recovery_pipeline.py tests/test_recovery_canary.py
tests/test_recovery_release.py -q`, затем полный pytest и Ruff. Эти тесты
используют временную SQLite, fake clock и подставные отправители/модель.
Проверяйте как флаг включён, так и rollback bridge при выключенном флаге.

Перед включением обязательны реальные API media/MID samples по TSK-012.
После выкладки с flags off событие `instagram.inbound.observed` содержит
SHA256(MID)[:16]: сравнивайте с хэшем Message.id из Conversations API, не
печатайте raw payload, токен или клиентскую переписку. `/api/admin/inbound-recovery`
использует прежний X-Admin-Token; публичный health содержит только флаги.
Живые HTTP/LLM прогоны и production rollout не входят в pytest.

Первое включение — `INBOUND_RECOVERY_SCOPE=allowlist` и CSV проверенных
числовых `INBOUND_RECOVERY_CLIENT_IDS`; пустой/некорректный allowlist при
enabled запрещён. `all` задаётся явно при отдельном расширении. Scope охватывает
scanner, jobs, legacy pending и send boundary, а не только входящий webhook.
Baseline canary и первого all различаются; перезапуск их не передвигает.
API shares permalink использует старый resolver; is_unsupported сохраняет
причину неполноты. Фото/два прямых видео доступны в живом API; конкретные
голосовое/post недоступны. Rollout: `.kiro/specs/inbound-recovery/rollout.md`.
`scripts/recovery_release.py` только готовит/проверяет пакет и backup,
не выполняет deployment/restart или изменение настроек.
