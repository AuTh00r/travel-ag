# Запуск бота на офисном Windows-сервере — полный гайд с нуля

Гайд под конкретную ситуацию:

- **Домашний ПК** — где ты правишь код (путь `D:\projects\travel-agent-bot`).
- **Офисный сервер** — отдельный Windows-ПК в офисе, который будет крутить бота 24/7. Кода на нём пока нет.
- **Домен** — `sundita.online`, уже подключён к Cloudflare (отдельный домен под бота; сайт фирмы `sundita.by` не трогаем).

Логика деплоя: код едет на сервер **через GitHub** (`git clone`), два секретных файла — **вручную**
(их в GitHub нет), а публичный адрес даёт **Cloudflare Tunnel**.

> Термины: «сервер» = офисный ПК. Он должен быть **всегда включён и не спать**, иначе бот не отвечает.
> `.env` и `credentials.json` — секретные файлы (ключи доступа), лежат в `.gitignore`, в облако не попадают.

---

## Что нужно иметь под рукой

- Логин и пароль от офисного Windows-ПК ✅ (есть).
- Домен `sundita.online` в статусе **Active** в Cloudflare ✅.
- Свой Google-аккаунт (для удалённого доступа).
- Домашний ПК с файлами `.env` и `credentials.json` в `D:\projects\travel-agent-bot`.

---

## Фаза 1. Один поход к офисному ПК (физически)

Пока на сервере не настроен удалённый доступ — подключиться к нему из дома нельзя. Поэтому первый
заход — руками, на месте. Сел за офисный ПК, вошёл по паролю, и:

### 1.1. Отключить сон
Параметры → Система → Питание → во всех пунктах сна поставь **«Никогда»**.

### 1.2. Настроить удалённый доступ (Chrome Remote Desktop)
1. Открой на сервере **Chrome** → https://remotedesktop.google.com/access
2. Войди в свой **Google-аккаунт** (с него же будешь подключаться из дома).
3. **«Настроить удалённый доступ»** → скачай и установи хост → задай **имя** ПК и **PIN-код** (запомни).
4. Готово. Больше к этому ПК физически ходить не придётся.

### 1.3. Проверка из дома
С домашнего ПК зайди на https://remotedesktop.google.com/access под тем же Google-аккаунтом →
увидишь офисный ПК → подключись по PIN. Дальше **всё делаешь из дома**, как будто сидишь за сервером.

---

## Фаза 2. Установить на сервер Docker и Git (один раз)

Всё дальше — уже удалённо, через Chrome Remote Desktop.

1. **Docker Desktop** — https://www.docker.com/products/docker-desktop
   - установи (всё по умолчанию) → **перезагрузи сервер** (после перезагрузки переподключись
     удалённым столом);
   - запусти Docker Desktop (🐳), дождись **зелёного кита** внизу слева;
   - Settings → General → включи **Start Docker Desktop when you log in**.
2. **Git for Windows** — https://git-scm.com/download/win (всё по умолчанию).

Проверка (открой на сервере **PowerShell**):
```powershell
docker --version
git --version
```
Обе команды показывают версию — идём дальше.

---

## Фаза 3. Скачать код и перенести секреты

### 3.1. Скачать код с GitHub (на сервере, в PowerShell)
```powershell
cd C:\
git clone https://github.com/AuTh00r/travel-ag.git travel-agent-bot
cd C:\travel-agent-bot
```
Теперь код лежит в `C:\travel-agent-bot` (это путь на сервере, не домашний `D:\...`).

### 3.2. Перенести 2 секретных файла (их нет в GitHub!)
С **домашнего** ПК возьми два файла:
- `D:\projects\travel-agent-bot\.env`
- `D:\projects\travel-agent-bot\credentials.json`

и положи их в `C:\travel-agent-bot\` **на сервере**. Способы:
- через буфер обмена Chrome Remote Desktop (открой файл дома в «Блокноте», скопируй всё,
  вставь на сервере в файл с тем же именем), или
- отправь себе файлы в Telegram/Google Drive и скачай на сервере, или
- флешкой (если бываешь в офисе).

Проверь, что оба файла на месте (на сервере):
```powershell
cd C:\travel-agent-bot
dir .env, credentials.json
```
Должны быть видны обе строки.

---

## Фаза 4. Запустить бота

На сервере, из папки проекта:
```powershell
cd C:\travel-agent-bot
docker compose up -d --build
```
- `--build` собирает «коробку» с ботом. **В первый раз 5–10 минут** (качается PyTorch) — это норма.
- `-d` — запуск в фоне.

Проверить, что бот живой (на самом сервере):
```powershell
curl http://localhost:8000/health
```
Ответ `{"status":"ok"}` — **бот работает** 🎉

Логи (что бот делает):
```powershell
docker compose logs -f
```
Выход из логов — `Ctrl+C` (бот продолжит работать).

> Сейчас бот работает, но из интернета ещё не виден. Даём адрес в Фазе 5.

---

## Фаза 5. Публичный HTTPS-адрес через Cloudflare Tunnel

Домен `sundita.online` уже в Cloudflare (Active). Осталось «пробить» туннель с сервера наружу —
роутер и белый IP не нужны.

### 5.1. Создать туннель в дашборде Cloudflare
1. https://dash.cloudflare.com → слева **Zero Trust** → **Networks → Tunnels** → **Create a tunnel**.
   - Если попросит план — выбери **Free ($0)** (могут попросить карту для активации Zero Trust,
     но списаний нет).
2. Тип коннектора — **Cloudflared**. Имя туннеля — `travelbot`. **Save**.
3. Cloudflare покажет команду установки под **Windows**. Открой на сервере **PowerShell от имени
   администратора** и выполни то, что он показал. Обычно это:
   ```powershell
   winget install --id Cloudflare.cloudflared
   cloudflared service install <ДЛИННЫЙ_ТОКЕН_ОТ_CLOUDFLARE>
   ```
   Эта команда ставит cloudflared **как службу Windows** — он будет стартовать сам после перезагрузки.
4. В дашборде дождись, пока статус коннектора станет **Connected/Healthy**, нажми **Next**.

### 5.2. Привязать домен к боту
Вкладка **Public Hostname** → **Add a public hostname**:
- **Subdomain:** оставь **пустым** (используем корень домена)
- **Domain:** `sundita.online`
- **Type:** `HTTP`
- **URL:** `localhost:8000`
- **Save**

### 5.3. Проверить снаружи
С телефона (по мобильному интернету, не по офисному Wi-Fi) открой:
```
https://sundita.online/health
```
`{"status":"ok"}` — **публичный адрес готов** ✅
Адрес webhook: `https://sundita.online/webhook/instagram`

---

## Фаза 6. Подключить webhook в Instagram (Meta)

1. https://developers.facebook.com → твоё приложение → **Webhooks** (или Instagram → Configuration).
2. **Edit / Add Callback URL**:
   - **Callback URL:** `https://sundita.online/webhook/instagram`
   - **Verify Token:** ровно значение `INSTAGRAM_VERIFY_TOKEN` из `.env`.
3. **Verify and Save**. Meta проверит адрес — бот ответит автоматически.
4. Подпишись на события сообщений (поле `messages`) для Instagram.

**Проверка, что сообщения доходят.** Напиши боту в Instagram, открой:
```
https://sundita.online/webhook/instagram/last_seen
```
- `{"received_ever":true, ...}` — всё работает;
- `{"received_ever":false}` — приложение Meta не в **Live Mode** или аккаунт не в ролях приложения.

---

## Повседневная эксплуатация

Все команды — на сервере (через удалённый стол), из `C:\travel-agent-bot`.

**Обновить бота после правок кода:**
```powershell
# дома: правишь код, потом
git add -A && git commit -m "что изменил" && git push

# на сервере:
cd C:\travel-agent-bot
git pull
docker compose up -d --build
```
Секретные файлы (`.env`, `credentials.json`) уже на сервере — их трогать не надо.

**Прочие команды:**
```powershell
docker compose logs -f        # логи в реальном времени (выход Ctrl+C)
docker compose restart        # перезапустить
docker compose down           # остановить
docker compose up -d          # запустить снова
```

**Сбросить сессии (если бот «запутался»):**
```powershell
docker compose down
del data\sessions.db
docker compose up -d
```

**Бэкап (раз в неделю).** Скопируй с сервера папку `data\` и файлы `.env`, `credentials.json`
на флешку/в облако.

**Автозапуск после перезагрузки** уже настроен: `restart: unless-stopped` в `docker-compose.yml`
поднимет бота, cloudflared стоит службой Windows. Условия — Docker Desktop стартует при входе
(Фаза 2), сервер не спит (Фаза 1) и в него выполнен вход в Windows.

---

## Если что-то не работает

| Симптом | Что проверить |
|---|---|
| Не подключается удалённый стол | Сервер выключен/спит/нет интернета. Проверь физически или попроси коллегу в офисе. |
| `curl http://localhost:8000/health` молчит | Бот не запустился. `docker compose logs --tail 100` — обычно ошибка в `.env`. Кит Docker зелёный? |
| Снаружи `https://sundita.online/health` не открывается | Cloudflare → Zero Trust → Tunnels: статус туннеля должен быть **Healthy**. Домен **Active**? |
| Meta не сохраняет webhook | `INSTAGRAM_VERIFY_TOKEN` в `.env` ≠ Verify Token в Meta, либо адрес без `/webhook/instagram`. |
| Сообщения не приходят (`received_ever:false`) | Приложение Meta не в Live Mode, или Instagram-аккаунт не в ролях приложения. |
| Заявки не пишутся в Google Sheets | Таблица не «расшарена» на сервисный аккаунт из `credentials.json`. |

Альтернативные способы (свой белый IP без Cloudflare и пр.) — в `docs/SELF-HOSTING.md`.

---

## Краткая шпаргалка (когда всё настроено)

```powershell
cd C:\travel-agent-bot
docker compose up -d --build   # запустить/обновить
docker compose logs -f         # логи
docker compose restart         # перезапуск
git pull; docker compose up -d --build   # выкатить новую версию кода
```

Адреса:
- Здоровье: `https://sundita.online/health`
- Webhook: `https://sundita.online/webhook/instagram`
- Диагностика webhook: `https://sundita.online/webhook/instagram/last_seen`
