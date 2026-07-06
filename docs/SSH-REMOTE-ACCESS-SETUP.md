# Удалённый SSH-доступ к серверу через Cloudflare Tunnel

> Статус: **рабочая инструкция**
> Дата: 2026-07-06
> Назначение: дать разработчику возможность заходить на сервер и выполнять
> команды (git pull, перезапуск бота) без ручного управления через Chrome
> Remote Desktop.
>
> Предполагает, что `docs/DEPLOY-WINDOWS.md` уже выполнен — сервер настроен,
> Cloudflare Tunnel для `sundita.online` работает.

## Термины

- **Сервер** — Windows-компьютер, который крутит бота 24/7
  (`C:\travel-agent-bot`), настроен по `docs/DEPLOY-WINDOWS.md`.
- **Клиент** — компьютер разработчика (офисный ПК), с которого будет
  устанавливаться SSH-подключение к серверу.
- **SSH** — протокол для удалённого доступа к командной строке.
- **Cloudflare Tunnel (cloudflared)** — уже установленная на сервере программа,
  которая пробрасывает сервер наружу без открытия портов на роутере. Сейчас
  через неё работает `sundita.online:443` → `localhost:8000`. Добавляется
  второй маршрут для SSH.
- **Cloudflare Access** — бесплатный сервис, который перед пропуском запроса
  в тоннель требует подтверждения личности (одноразовый код на почту).

---

## Модель безопасности

Эта настройка добавляет **постоянный** способ попасть в консоль сервера из
интернета:

- На пользователе Windows на сервере должен быть надёжный пароль.
- Доступ получит любой, кто пройдёт Cloudflare Access (твой email + код из
  письма) **и** имеет SSH-ключ.
- Рекомендуется ограничить Cloudflare Access policy **одним твоим email**, а
  не оставлять открытой.

---

## Фаза 1. Включить OpenSSH Server на сервере

Выполняется **один раз** через Chrome Remote Desktop (займи 5 минут).

### 1.1. Установить компонент

PowerShell **от администратора** на сервере:

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
```

### 1.2. Запустить службу и включить автозапуск

```powershell
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'
```

### 1.3. Разрешить порт 22 в брандмауэре Windows

Правило обычно создаётся автоматически. Проверить:

```powershell
Get-NetFirewallRule -Name *ssh*
```

Если правила нет:

```powershell
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

### 1.4. Задать/проверить пароль пользователя

Пароль — единственная защита самого SSH (Cloudflare Access — внешняя).

1. **Параметры → Учётные записи → Параметры входа** — задай надёжный пароль.
2. Запомни имя пользователя (оно понадобится). Узнать:
   ```powershell
   whoami
   ```

---

## Фаза 2. Добавить SSH-маршрут в Cloudflare Tunnel

Тоннель `travelbot` уже существует. Добавляется **второй маршрут** в том же
тоннеле.

### 2.1. Открыть настройки тоннеля

`https://one.dash.cloudflare.com` → **Networks → Connectors** → выбрать
тоннель `travelbot` → **Routes**.

### 2.2. Добавить маршрут для SSH

- **Subdomain / Hostname:** `ssh` (будет `ssh.sundita.online`)
- **Domain:** `sundita.online`
- **Service:** `SSH` → `localhost:22`

### 2.3. Защитить маршрут через Cloudflare Access

`one.dash.cloudflare.com` → **Access → Applications** → **Add an application**
→ **Self-hosted**:

- **Application domain:** `ssh.sundita.online`
- **Policy name:** `SSH access`
- **Action:** Allow
- **Session duration:** до 24 ч, чтобы не вводить код каждый раз
- **Configure rules:** `Emails` → укажи свой email (тот же, что в Google)

**Без этого шага не продолжай!** Без Access SSH-порт будет доступен любому.

---

## Фаза 3. Настроить клиент (офисный ПК)

### 3.1. Установить `cloudflared`

PowerShell **от администратора** на клиенте:

```powershell
winget install --id Cloudflare.cloudflared
```

Проверить:

```powershell
cloudflared version
```

### 3.2. Настроить SSH config

На клиенте создай/отредактируй `~\.ssh\config`:

```
Host sundita-office
  HostName ssh.sundita.online
  User <ИМЯ_ПОЛЬЗОВАТЕЛЯ_WINDOWS>
  ProxyCommand cloudflared access ssh --hostname %h
```

Замени `<ИМЯ_ПОЛЬЗОВАТЕЛЯ_WINDOWS>` на то, что показала `whoami` на сервере
(например, `Admin` или `User`).

### 3.3. Добавить публичный SSH-ключ на сервер (ключ уже есть)

На клиенте уже есть ключ `~\.ssh\id_ed25519_travelbot`. Его нужно скопировать
на сервер, чтобы не вводить пароль каждый раз:

**Вариант A — через Chrome Remote Desktop (проще):**
1. Открой `~\.ssh\id_ed25519_travelbot.pub` на клиенте (блокнот).
2. Скопируй содержимое.
3. Через Chrome Remote Desktop на сервере выполни в PowerShell:
   ```powershell
   Add-Content -Path "$env:USERPROFILE\.ssh\authorized_keys" -Value "<ВСТАВЬ_СОДЕРЖИМОЕ_КЛЮЧА>"
   ```

**Вариант B — через ssh-copy-id (если SSH уже работает):**
```powershell
type $env:USERPROFILE\.ssh\id_ed25519_travelbot.pub | ssh sundita-office "mkdir -Force $env:USERPROFILE\.ssh; Add-Content -Path $env:USERPROFILE\.ssh\authorized_keys -Value @($input)"
```

### 3.4. Первое подключение

```powershell
ssh sundita-office
```

При первом запуске `cloudflared access` откроет браузер — введи email, получи
код из письма. После этого SSH попросит пароль Windows — введи его один раз
(если не скопировал ключ на шаге 3.3).

Проверь, что работает без пароля (по ключу):

```powershell
ssh sundita-office "echo SSH_OK"
```

### 3.5. Второй хост для прямого деплоя (без Cloudflare Access)

Если используется поддомен, отличный от `ssh.sundita.online`, добавь второй
хост в `~\.ssh\config`:

```
Host sundita-deploy
  HostName ssh.sundita.online
  User <ИМЯ_ПОЛЬЗОВАТЕЛЯ_WINDOWS>
  ProxyCommand cloudflared access ssh --hostname %h
```

Либо используй один `sundita-office` — этого достаточно.

---

## Фаза 4. Проверка

```powershell
ssh sundita-office "echo ok"
# → ok

ssh sundita-office "cd C:\travel-agent-bot && git status"
```

Если это работает — деплой можно делать одной командой:

```powershell
ssh sundita-office "cd C:\travel-agent-bot && git pull && .venv\Scripts\pip install -r requirements.txt -q && .venv\Scripts\python -m pytest tests -q"

ssh sundita-office "taskkill /f /im uvicorn.exe; C:\travel-agent-bot\start-bot.vbs"

curl https://sundita.online/health
```

**Готовый скрипт:** `deploy.ps1` в корне проекта — делает то же самое одной
командой.

---

## Откат / отключение

1. Cloudflare Dashboard → Access → Applications → удалить `ssh.sundita.online`
   — доступ снаружи сразу пропадёт.
2. Опционально — удалить маршрут в тоннеле (Routes → удалить запись).
3. Опционально — остановить службу на сервере:
   ```powershell
   Stop-Service sshd
   Set-Service -Name sshd -StartupType 'Disabled'
   ```

## Ссылки

- Базовая настройка сервера — `docs/DEPLOY-WINDOWS.md`
- Скрипт быстрого деплоя — `deploy.ps1` (корень проекта)
- Cloudflare Access — `one.dash.cloudflare.com`
- Тоннель — Cloudflare → Networking/Networks → `travelbot`
- Публичный ключ: `~\.ssh\id_ed25519_travelbot.pub` (на клиенте)
