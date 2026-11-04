---
status: old-subscriptions-disabled-source-correlation-pending
date: 2026-10-18
scope: authorized old-app messages unsubscribe; working app read-only
---

# Несколько приложений указывают на один webhook

Symptom: часть входящих POST отклоняется как signature mismatch; тела и
подписи не сохраняются. Контрольное сообщение тестера 20:16:36 Minsk прошло
webhook, затем появилось также через API. Job cancelled/manager_takeover,
новых отправок по нему нет. Это доказывает работоспособность основного
маршрута, но не устанавливает источник других отклонённых POST.

Read-only checks:

- Messaging token действителен, type PAGE, app_id1133220645701291,
  application Travel-agent-bot-new, profile_id100373865233538. App credentials
  успешно читают subscriptions. Секреты и токены в результаты не выводились.
- Page subscribed_apps: только Travel-agent-bot-new, subscribed_fields messages.
- App subscriptions: instagram/messages и page/messages активны, v26.0,
  оба callback https://sundita.online/webhook/instagram.
- В authenticated developer dashboard старый Travel Bot Test1
  (1548133150338782, development mode) также имеет этот callback для Instagram
  и Page; у обоих messages подписан на v25.0.
- У Travel-ag-bot2 (1582584650101427) и Travel Bot Tests (1396801762315661)
  в доступном Instagram Login setup callback пуст. Это не полный аудит всех
  недоступных API-подписок этих приложений: общий Webhooks route второго
  приложения перенаправляет на dashboard, Facebook Login setup показывает
  инструкцию без callback.

Interpretation: старый Test1 — подтверждённый кандидат на лишний источник
с другим app secret. Но наличие callback не доказывает, что наблюдавшиеся
отказы пришли от него; development mode дополнительно ограничивает реальные
события. Подпись конкретного отклонённого POST не сопоставлена с его ключом.
Не утверждать, что signature mismatch безопасен или потеря заявок исключена.

Изменение 2026-10-18: после инструкции по двум переключателям владелец
согласовал «+», затем сообщил «отключил». Свежая проверка показала Page=false,
Instagram=true. Агент отключил только оставшийся Instagram/messages в старом
1548133150338782; повторное чтение после reload подтвердило false, Page также
false. Время подтверждения обеих off: 17:49:39Z (20:49:39 Minsk).
Callback обоих объектов сохранён. Остальные переключатели не менялись;
приложения/секреты/права/код/БД не изменялись. Исходная активная версия была
v25.0; сразу после выключения UI ещё показывал v25.0, после reload Meta
показывает default v26.0 у неактивного поля. Версия вручную не переключалась.
Откат: только при отдельном разрешении вернуть messages обоих объектов,
выбрав исходную v25.0. Приложение и callback сохранены для обратимости.

Postcondition 17:50:23Z: рабочее приложение1133220645701291 по Graph API
по-прежнему имеет active instagram/messages + page/messages на прежний
callback. Health ok; recovery/reconcile flags прежние. За10мин перед
границей17:49:39Z:19 mismatch. Последний наблюдавшийся отказ17:47:56Z;
первые44сек после границы без новых событий. Этот короткий срез не доказывает
устранение причины; нужен следующий срез и новый контрольный webhook.
Снимок off-переключателя сохранён в артефакте задачи
old-test1-instagram-messages-off.jpg. Запрошен новый контрольный текст
«Проверка подписи 2049»; отправку самим агентом не выполнять.

Срез17:52:21Z:162сек после подтверждения off,0 signature mismatch,
последний отказ17:47:56.634739Z. За предыдущие10мин было19. После границы
есть10 message.received (возможна API-нормализация, не доказательство нового
webhook); healthok. Контроль2049 в журнале пока отсутствует. Короткое отсутствие
отказов поддерживает гипотезу, но не является доказательством источника старых
POST или гарантией приёма новых сообщений; контрольный webhook ещё ожидается.

Контроль завершён: «Проверка подписи 2049», event_time1792346201.268
(20:56:41.268 Minsk), received1792346203.6351628; sources=[api,webhook].
Job cancelled/manager_takeover, deliveries=[]; manager pause активна.
Сообщение прошло проверку подписи и не потерялось. Срез17:57:45.900748Z:
486сек после подтверждения off,0 новых signature mismatch и0 перечисленных
runtime/model/reconcile errors;2 webhook.received, healthok. Последний отказ
остаётся17:47:56.634739Z. Отсутствие отказов после отключения поддерживает
гипотезу старого Test1, но не сопоставляет подпись конкретных старых POST.

Primary API references (Meta docs retrieved through Context7):
- https://developers.facebook.com/docs/graph-api/reference/debug_token
- https://developers.facebook.com/docs/graph-api/reference/page/subscribed_apps
- https://developers.facebook.com/docs/graph-api/reference/app/subscriptions

Page edge сам по себе не подтверждает всю конфигурацию Instagram. App
subscriptions показывает только конкретное приложение, не всех отправителей
на общий URL. IP/User-Agent/совпадение времени не доказывают подлинность POST.
