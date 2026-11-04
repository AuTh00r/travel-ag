# Компактные Telegram-уведомления — выкладка 2026-10-19

## Контекст

Пользователь просил выложить новые изменения из облачного чата «Упростить
логи Google Docs» и отдельно подтвердил «Нет, выложить только новые правки
кода». Расширение inbound recovery на всех остаётся отложенным.

В origin/master один новый commit b0c04146e3177e32b1fbaa788524417570a077f5:
tour-sync diff formatting и тестовые метки Telegram. Git pull сначала
блокировался рабочими изменениями Telegram. К моменту нашего preflight
пользователь уже обновил серверный HEAD до b0c04146, но работающий PID4136
оставался от18Oct17:07 UTC; рестарт не произошёл.

## Причина необходимости объединения

Новый cloud commit основан на старой Telegram-реализации, без введённых
позже receipt/transport/recovery guards. На диске два известных несовпадения
с installed manifest: telegram_notify.py и его тест. Простая замена всего
сервиса потеряла бы guards. Новые format hunks перенесены поверх текущей
проверенной версии; сохранены deferred notifications, scope/destination
checks, message_id receipts, unknown/retry/partial semantics и безопасные логи.
Добавлен точный actual handle _shelter_0, без расширения recovery allowlist.

## Проверки

- Сохранены source/test snapshots server-before и local-before без секретов.
- Сначала новые tests: 12 RED/1 PASS/69 deselected; после интеграции166
  профильных PASS/19.92 с. Полный pytest1503 PASS/8 прежних warnings/68.97 с.
- Ruff/diff и два read-only review кода/контроллера PASS.
- Offline controller proof: inverse и partial rollback возвращают последнюю
  проверенную1486 PASS версию четырёх файлов; новые receipts/unknown SQLite
  сохраняются, неожиданные target/env изменения блокируют действие. Network0.

## Факт выкладки

Package telegram-compact-20261019, SHA256
d14f70bbbab1f67562582d22ee2b9b9f7bf64a6734a0f6ee02c17ed139729c14.
Обновлены два source, два test и runtime manifest31. Prepare/apply/verify exit0;
backup исходного checkout и SQLite online backup integrity PASS. Manifest
учитывает фактические файлы после git pull; прочие SHA защищены. Fallback
отдельно сохраняет последнюю известную рабочую receipt-aware версию.

PID4136→12960, start2026-10-19T11:20:54.3458409Z (14:20:54 Минск).
Healthok; 31 SHA и installed manifest совпали. .env, credentials/launchers,
scope/baseline сохранены, recovery allowlist одного тестера. БД не заменялась,
паузы/история/лимиты не сбрасывались. Общая recovery baseline не создавалась.

Installed smoke отдельным процессом: raw Docs summary, exact test labels,
preview только для tour_sync, возврат receipt987 на mocked HTTP, компактная
сводка и UTF16 bound PASS. Реальных model/Telegram/Instagram sends не было.
На контрольном чтении11:21:58 UTC в bot.log после restart нет error/warning;
tours.ready и tours.published наблюдаются. Это snapshot, не фоновый монитор.

## Границы

Рабочая Git-копия остаётся с прежними незакоммиченными изменениями;
stash/reset/commit/push не выполнялись. Для следующих cloud-правок также
нужна сверка с установленными source, а не слепой git pull. Системный формат
не проверяли ручной отправкой настоящим менеджерам; transport smoke и тесты
использовали заглушки. Новые правила применятся при следующем штатном событии.
