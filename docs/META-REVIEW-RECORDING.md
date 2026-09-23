# Запись видео для повторного Meta App Review

Приложение: Travel-agent-bot-new, `1133220645701291`.
Страница: «Сандита», `100373865233538`. Instagram: `@sundita.travel`.

## Простой режим: любые новые сообщения

Для записи с единственным тестовым клиентом достаточно:

```powershell
cd D:\projects\travel-agent-bot
.\.venv\Scripts\python.exe scripts/meta_review.py watch
```

После `INSTRUCTIONS` отправлять любые обычные вопросы в Instagram.
Скрипт показывает новые события сервера и новые сохранённые сообщения всех
диалогов, не выводя историю, существовавшую при запуске. Наблюдение продолжается
до Ctrl+C, в том числе после первого ответа. `SAVED OUTGOING MESSAGE` — запись
из истории; успешную отправку API подтверждает отдельное событие
`instagram.message.sent`, а доставку — окно Instagram клиента.

Метки в сценариях ниже теперь необязательны: можно заменить каждую команду
`watch --marker ...` на `watch` и отправить произвольный вопрос.
Для ограничения времени использовать `--timeout 240`.

## Окна для записи

1. [Основные настройки приложения](https://developers.facebook.com/apps/1133220645701291/settings/basic/).
2. [Подписка на Page Webhooks](https://developers.facebook.com/apps/1133220645701291/webhooks/?view=page).
3. [Instagram Direct](https://www.instagram.com/direct/inbox/) под тестовым клиентом;
   открыть переписку с [sundita.travel](https://www.instagram.com/sundita.travel/).
4. PowerShell на рабочем компьютере с проектом `D:\projects\travel-agent-bot`.

Подготовить тестового клиента с ролью в приложении. Менеджер не должен отвечать
от имени компании в этом диалоге перед тестом: такое вмешательство ставит бота
на паузу. Использовать собственные тестовые данные.

## До включения записи

В PowerShell выполнить:

```powershell
cd D:\projects\travel-agent-bot
.\.venv\Scripts\python.exe scripts/meta_review.py status
```

Если Cloudflare откроет страницу входа, пройти авторизацию до записи и повторить
команду. Успех: `CONNECTED ASSETS` с нужной страницей и Instagram, затем
`CURRENT APP SUBSCRIPTION` с нужным App ID и `messages`.

Скрипт выполняет команды через уже настроенный SSH `sundita-office` на сервере
`C:\travel-agent-bot`. Токен берётся из серверного `.env` и не выводится. Загружать
скрипт на сервер или перезапускать бота не нужно.

## Видео 1: pages_manage_metadata

1. Включить запись. Показать название и ID приложения в Basic Settings.
2. Выполнить `status`, показать соответствующие Page ID, Instagram и подписку.
3. В том же PowerShell выполнить:

   ```powershell
   .\.venv\Scripts\python.exe scripts/meta_review.py subscribe
   ```

   **Эта команда реально повторно применяет подписку `messages` к текущему
   приложению**, сохраняя все остальные поля подписки. Показать строку POST,
   HTTP 200 и `VERIFIED SUBSCRIPTION`. Ничего удалять или отключать в Dashboard
   перед этим не нужно.

4. Запустить наблюдение:

   ```powershell
   .\.venv\Scripts\python.exe scripts/meta_review.py watch --marker REVIEW-META-1509-A
   ```

5. Дождаться `INSTRUCTIONS`, затем от тестового клиента отправить в Instagram:

   ```text
   REVIEW-META-1509-A. Расскажите о туре От Дуная до Босфора.
   ```

6. Дождаться ответа и показать строки `ACTUAL SERVER LOG` с событиями
   `instagram.message.received`, `instagram.message.processing`,
   `instagram.message.sent`. Показать тот же ответ в Instagram клиента.

## Видео 2: instagram_manage_messages

1. Начать новую запись. Показать приложение и выполнить `status`.
2. Запустить:

   ```powershell
   .\.venv\Scripts\python.exe scripts/meta_review.py watch --marker REVIEW-DM-1509-B
   ```

3. После `INSTRUCTIONS` отправить от тестового клиента:

   ```text
   REVIEW-DM-1509-B. Расскажите о туре От Дуная до Босфора.
   ```

4. Показать `SAVED INCOMING TEST MESSAGE`, реальные события сервера, затем
   `SAVED BOT REPLY AFTER SUCCESSFUL SEND API CALL` с текстом ответа.
5. Переключиться в Instagram клиента и показать доставленный ответ с тем же текстом.

Каждый повтор записи требует новой метки, например `REVIEW-DM-1509-C`.
Метка в команде и в сообщении должна совпадать. Если метка уже есть в истории,
скрипт остановится, чтобы не выдать старую переписку за новый тест.

## Что именно показывает терминал

`watch` читает существующие логи и базу сессий только для сообщения с указанной
меткой. Он не отправляет сообщения, не вызывает AI и не меняет данные. Ответ
создаёт и отправляет работающий бот. Полный текст появляется после обработки
AI и сохранения в базу; это не вывод сырого webhook в момент получения.
Событие `message.sent` подтверждает успешное завершение Send API в коде бота;
доставку клиенту необходимо показать отдельно в Instagram.

Если с параметром `--timeout 240` ответ не подтверждён за четыре минуты,
режим с меткой завершится с объяснением. По умолчанию время не ограничено.
Не отправлять в этот момент много повторов. Проверить роли тестового аккаунта
и паузу менеджера. Ctrl+C останавливает только наблюдение.

## Английское пояснение для видео и заявки

```text
This is a server-side automated assistant for Sandita's own Instagram account.
The business administrator authorizes the connected Facebook Page through Meta.
Customers interact with the assistant in Instagram Direct; there is no separate
customer-facing Facebook Login or messaging interface on our website.

The terminal demonstrates the actual Page subscription operation and a read-only
view of the running application's logs and saved test conversation. It is not a
manual sending interface. An incoming Instagram message triggers the bot's reply
automatically through the Meta Send API. The same reply is then shown in Instagram.
The integration uses a Facebook Page access token.
```

Если записывается предоставление разрешений администратором через Meta, снимать
экраны выбора активов и согласия, скрыв пароли и токены. Для этого не отзывать
существующий доступ и не называть Page-токен токеном системного пользователя.
Успешная демонстрация отвечает на замечания ревьюера, но не гарантирует одобрение.
