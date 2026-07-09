# Деплой на сервер

## Быстрый деплой (после изменений)

```powershell
.\deploy.ps1
```

Скрипт делает всё автоматически:
1. Коммитит и пушит в `origin master`
2. Проверяет SSH-доступ
3. Пуллит код на сервере и устанавливает зависимости
4. (Опционально) запускает тесты
5. Перезапускает бота через планировщик задач
6. Ждёт health check

Параметры:
```powershell
.\deploy.ps1 -SkipTests          # без тестов
.\deploy.ps1 -SkipPush           # без пуша (если уже запушили руками)
.\deploy.ps1 -CommitMessage "fix" # свой коммит
```

## Вручную (пошагово)

```powershell
# 1. Закоммитить и запушить
git add -A
git commit -m "краткое описание"
git push origin master

# 2. Зайти на сервер, стянуть код и обновить зависимости
ssh sundita-office
chcp 65001
cd C:\travel-agent-bot
git pull origin master
.venv\Scripts\pip install -r requirements.txt -q
# или одной строкой:
ssh sundita-office "chcp 65001 >nul & cd C:\travel-agent-bot & git pull origin master & .venv\Scripts\pip install -r requirements.txt -q"

# 3. Запустить тесты
ssh sundita-office "chcp 65001 >nul & cd C:\travel-agent-bot & .venv\Scripts\python -m pytest tests -q"

# 4. Перезапустить бота
ssh sundita-office "chcp 65001 >nul & schtasks /run /tn RestartTravelBot"

# 5. Проверить
curl https://sundita.online/health
# → {"status":"ok"}
```

## Сброс сессий (если контекст засорён)

```powershell
ssh sundita-office "chcp 65001 >nul & cd C:\travel-agent-bot & del /q data\sessions.db"
# Бот сам создаст новую БД при следующем запросе.
```

## Сброс takeover (паузы бота) для конкретного клиента

```powershell
ssh sundita-office "chcp 65001 >nul & cd C:\travel-agent-bot & .venv\Scripts\python -c ^
import sqlite3, json; conn = sqlite3.connect('data/sessions.db'); ^
[conn.execute('UPDATE sessions SET state=? WHERE client_id=?', ^
 (json.dumps({**json.loads(s), 'manager_last_at': None}), cid)) ^
 for cid,s in conn.execute('SELECT client_id, state FROM sessions').fetchall()]; ^
conn.commit(); conn.close(); print('Done')"
```

## Просмотр логов

```powershell
# Через Chrome Remote Desktop — открыть лог-файл на сервере вручную.
# Либо через SSH (для простых команд):
ssh sundita-office "chcp 65001 >nul & type C:\travel-agent-bot\nohup.out 2>nul | tail -50"
```

## Проверка статуса

```powershell
# Health
curl https://sundita.online/health

# Проверить, приходят ли вебхуки от Instagram
curl https://sundita.online/webhook/instagram/last_seen
# → {"received_ever":true,"last_received_at":"..."} — OK
# → {"received_ever":false} — вебхуки не приходят
```

## Ссылки

- **Домен**: `https://sundita.online`
- **Webhook**: `https://sundita.online/webhook/instagram`
- **Health**: `https://sundita.online/health`
- **SSH**: `ssh sundita-office` (настройка в `~\.ssh\config`)
- **Сервер**: Windows, проект `C:\travel-agent-bot`
- **Репозиторий**: `https://github.com/AuTh00r/travel-ag.git`
- **Деплой скрипт**: `deploy.ps1`
