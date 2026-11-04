# Cloudflare Access: app-info timeout при SSH/SCP

Дата:2026-10-15. Проверено при авторизованной выкладке N25+N26.

## Симптом и причина

SSH/SCP периодически завершаются255 до запуска удалённой команды:
`failed to get app info: Head ... context deadline exceeded`.
Упоминание login/URL в общем stderr не доказывает истечение сессии. Владелец
указал трёхдневную сессию; обычная SSH read-only команда затем прошла без входа.
Подтверждён транспортный app-info timeout, не установленная ошибка авторизации.

## Рабочий путь и границы

Не менять policy/credentials и не просить повторный вход только по substring.
Скрывать целые URL/JWT до вывода диагностики. SCP продолжал падать; передача
через обычный тот же авторизованный SSH stdin завершилась успешно: JSON/base64,
allowlist filenames, точный staging root, expected SHA и запрет неожиданного
существующего файла. Это смена транспорта файлов, не обход Access.

Только preflight/verify и idempotent staged transfer безопасно повторялись до3раз
при подтверждённом app-info timeout. Apply не повторялся: при неопределённом
restart сначала отдельный verify файлов/PID/health. N26:29staged+installedcases,
23SHA и local/publichealthPASS. Сетевые тайм-ауты могут повториться; успешный SSH
не доказывает постоянную доступность. Реальные ссылки авторизации не сохраняются.
