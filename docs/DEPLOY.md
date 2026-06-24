# Деплой на VPS

## Быстрый деплой (после изменений)

```bash
# 1. Закоммитить и запушить
git add -A
git commit -m "краткое описание"
git push origin master

# 2. Зайти на VPS, стянуть код и перезапустить
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot
git pull origin master
systemctl restart travel-bot

# 3. Проверить
curl https://travelagenttest.duckdns.org/health
# → {"status":"ok"}
```

## Сброс сессий (если контекст засорён)

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot
rm -f data/sessions.db
systemctl restart travel-bot
```

## Просмотр логов

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
journalctl -u travel-bot -n 50 --no-pager    # последние 50 строк
journalctl -u travel-bot -f                   # в реальном времени
```

## Проверка статуса

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
systemctl status travel-bot --no-pager -l | head -10

# Проверить, приходят ли вебхуки от Instagram
curl http://127.0.0.1:8000/webhook/instagram/last_seen
# → {"received_ever":true,"last_received_at":"..."} — OK
# → {"received_ever":false} — вебхуки не приходят
```

## Полезные команды на VPS

```bash
# Редактировать .env
nano /opt/travel-agent-bot/.env

# Редактировать конфиг systemd
systemctl cat travel-bot

# Перезагрузить nginx
systemctl reload nginx
```

## Ссылки

- **Домен**: https://travelagenttest.duckdns.org
- **Webhook**: https://travelagenttest.duckdns.org/webhook/instagram
- **Health**: https://travelagenttest.duckdns.org/health
- **IP VPS**: `201.51.3.72`
- **SSH ключ**: `~/.ssh/id_ed25519_travelbot`
- **Репозиторий**: `https://github.com/AuTh00r/travel-ag.git`
