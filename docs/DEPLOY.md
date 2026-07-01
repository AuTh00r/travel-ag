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
source .venv/bin/activate
pip install -r requirements.txt
pytest tests/ -q

# Перезапустить процесс (если через systemd):
systemctl restart travel-bot

# Или если через screen/tmux:
# pkill -f "uvicorn src.main:app"
# nohup .venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8000 &

# 3. Проверить
curl https://travelagenttest.duckdns.org/health
# → {"status":"ok"}
```

## Сброс сессий (если контекст засорён)

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72
cd /opt/travel-agent-bot
rm -f data/sessions.db
# перезапустить бота
```

## Просмотр логов

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72

# Через journalctl (если systemd)
journalctl -u travel-bot -n 50 --no-pager

# Или через nohup-лог
tail -n 50 nohup.out
```

## Проверка статуса

```bash
ssh -i ~/.ssh/id_ed25519_travelbot root@201.51.3.72

# Проверить, приходят ли вебхуки от Instagram
curl http://127.0.0.1:8000/webhook/instagram/last_seen
# → {"received_ever":true,"last_received_at":"..."} — OK
# → {"received_ever":false} — вебхуки не приходят
```

## Ссылки

- **Домен**: https://travelagenttest.duckdns.org
- **Webhook**: https://travelagenttest.duckdns.org/webhook/instagram
- **Health**: https://travelagenttest.duckdns.org/health
- **IP VPS**: `201.51.3.72`
- **SSH ключ**: `~/.ssh/id_ed25519_travelbot`
- **Репозиторий**: `https://github.com/AuTh00r/travel-ag.git`
