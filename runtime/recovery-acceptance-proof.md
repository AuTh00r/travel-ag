# Сквозная приёмка восстановления — 2026-10-18

Статус: isolated proof PASS; production проверен только read-only.
Спека: `.kiro/specs/inbound-recovery/tasks.md`, TSK-023.

## Что проверяли

Ранее scanner и business pipeline были покрыты отдельными интеграционными
тестами. Добавлен единый сценарий без исходного webhook и без подмены
refresh_client: Graph-заглушка → SQLite → пересоздание store/service → реальный
business dispatch → сохранённый ответ → заглушка отправки с receipt.
Повторный startup/API и поздний webhook того же MID не создают новую задачу,
генерацию, отправку или историю. Проверяются исходный вопрос в сообщении модели
и истории, точный адресат/сохранённый текст отправки, sources api+webhook и
свежие API-чтения перед моделью и доставкой.

Два варианта: restart после scanner persist и restart после прерванного claim.
Во втором истекает lease; startup сохраняет один использованный технический
повтор и due через120 с, ранний tick не запускает обработку.
Перезапуск имитируется новыми экземплярами с прежней SQLite, процесс ОС не
останавливается. HTTP заблокирован общим fixture, модель и отправки — заглушки.

## Verification

- Исходные семь профильных файлов: 200 PASS/32.11 с.
- `tests/test_recovery_acceptance.py`: 2 PASS/13.50 с; после read-only review
  усилены проверки текста/адресата/freshness/sources, ещё2 PASS/14.04 с.
- Полный pytest: 1482 PASS/8 прежних warnings/67.87 с. Усиленные assertions
  дополнительно проверены отдельным прогоном после полного сбора тестов.
- Ruff нового теста и diff-check PASS. Runtime-код не менялся, деплой не нужен.

## Read-only production evidence

2026-10-18 18:04:12 UTC: recovery/reconcile остаются allowlist одного тестера;
активна менеджерская пауза от16:53:12 UTC. Новые контрольные события имеют
api+webhook, cancelled/manager_takeover и пустые deliveries.
Последняя сверка checked_at1792346595.6173286, gap=false.

18:06:58 UTC: для трёх уже завершённых задач тестера независимо прочитаны
четыре IG receipts через Meta Message API. HTTP200, точные receipt ID, текст
и получатель совпали с SQLite, каждый sent/attempts1. Две задачи answered,
одна human_only. У human_only есть четыре sent Telegram receipts с разными
назначениями, каждый attempts1; notification_counted=true. Это подтверждения
базы по Telegram, повторного чтения Telegram сообщений не делалось.
У всех трёх один исходный MID с api+webhook; технических повторов0.

Новых модельных вызовов/отправок/изменений БД, пауз, лимитов, настроек и
подписок диагностический процесс не делал. Отдельно запрошено согласие на
снятие только текущей тестовой паузы для нового live happy-path текущей сборки.

После отдельного ответа «Да, снять только паузу тестового аккаунта» выполнен
один POST к штатному admin reset-takeover через loopback сервера. В18:10:55 UTC
HTTP200/reset=true; пауза true→false, revision21→22. Полный hash остальных
полей сессии совпал, история и escalation_count сохранены; шесть прежних
cancelled задач сохранили state/reason/updated_at. Restart не делался.

## Новый живой happy-path текущей сборки

Пользователь подтвердил отправку «+». Новое сообщение получено
2026-10-18 18:11:28.493 UTC (21:11:28 Минск). Один входящий MID, одна задача
answered/done; в18:11:38.879492 UTC — один DeepSeek v4-flash text/tool_calls,
attempt1/validation valid, input20306/output452 tokens. Два фрагмента IG-ответа
sent/attempts1, оба receipt ID, полный текст и адресат подтверждены отдельными
GET Meta HTTP200. Это две части одного ответа, а не повторная генерация.
Own echoes распознаны как own_echo; ложной менеджерской паузы нет.

После очередного штатного scanner tick checked_at1792347196.4302847
(18:13:16 UTC), through1792347102, gap=false, scan_failures0. Контрольное
чтение18:13:42 UTC: тот же MID имеет api+webhook, по-прежнему одна задача,
один валидный ответ модели и две прежние доставки с attempts1. Пауза false,
технических и semantic повторов0. Новых ручных отправок, paid probe, restart
и смены scope проверяющий процесс не делал. Telegram для этого обычного
answered-запроса не планировался; ранее подтверждённые TG receipts описаны выше.

## Дополнительные отказы TSK-024

По запросу «давай еще тестов» добавлены четыре сквозных случая в том же
acceptance-файле. Runtime и production не менялись.

- Partial: модель выдаёт длинный ответ, первая IG-часть подтверждена, вторая
  получает явный rate limit. Новый store/service с прежней SQLite и настоящий
  refresh не повторяют первую часть и модель; вторая уходит ровно в due,
  с исходным сохранённым текстом. Проверены receipts/attempts, точная
  последовательность отправок, неизменный result и отсутствие дублей истории
  после ещё одного startup.
- Unknown: отдельно ReadTimeout и пустой receipt. После restart, настоящей
  API-сверки и дубля webhook остаётся unknown, сохранённый result не меняется,
  вторая часть не уходит, нет повторной генерации/отправки/legacy queue.
- Manager race: ainvoke остановлен asyncio.Event; настоящий manager event
  сохраняется до освобождения модели. Задача cancelled/manager_takeover,
  Instagram/Telegram не отправлены, result не сохранён; полный state/revision
  менеджера не перезаписан поздним ответом. Снятие паузы, restart и API-сверка
  не оживляют задачу.

Первый прогон3 FAIL/3 PASS выявил неверные новые ожидания истории, не runtime
регрессию: по design история user фиксируется до доставки, assistant — по
каждой подтверждённой части. Это проверено в design и record_delivery;
assertions исправлены на точные payload каждой sent части и сохранение
единственного user при unknown. Неослабленные проверки доставки/повторов PASS.
Read-only review подтвердил семантику и изоляцию; блокирующих замечаний нет.

Итог acceptance6 PASS/17.14 с, полный pytest1486 PASS/8 прежних warnings/
75.83 с; после review добавлены state/revision/result assertions manager race,
отдельно1 PASS/8.04 с. Ruff/diff PASS. Реальные HTTP в тестах запрещены,
SQLite временная.

## Живая группировка двух реплик

Пользователь подтвердил «+». Два входящих MID получены в18:21:47.564 UTC и
18:21:49.958 UTC (разница2.394 с), оба вошли в одну задачу с members2.
В сохранённом тексте есть и информация о визе, и запрос программы. Один
DeepSeek v4-flash text/toolcall, attempt1/valid в18:21:56.793817 UTC;
input20733/output288 tokens. Один IG-ответ sent/attempts1, receipt ID,
полный текст и получатель совпали с отдельным Meta GET HTTP200.

Повторное контрольное чтение18:23:57 UTC после штатной сверки
checked_at1792347796.6283357: у обоих MID api+webhook; одна answered/done
задача, прежний единственный модельный ответ и прежняя единственная доставка.
gap=false, through1792347718, технических/semantic повторов0; пауза false.
Проверяющий процесс был read-only; нового сброса, restart или смены scope нет.

## Сохраняющиеся границы

Конкурентный менеджер во время модели, partial/unknown и технические сбои
проверяются в существующем изолированном стенде; production намеренно не
останавливали и сбои отправки не создавали. Старые failed_final/cancelled
не переигрывались. API-only unsupported voice/post и непроверенные story/ad
образцы не объявляются восстановленными. Scope=all требует отдельного согласия.
