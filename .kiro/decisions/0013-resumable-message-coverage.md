# 0013. Resumable Message Coverage

## Status
accepted

## Context
Meta фактически вернула 21 запись при limit20, адаптер обрезал до20 и оставлял gap. Один page без сохранённого message cursor не закрывает разрыв после длительного простоя. Владелец одобрил корректное постраничное чтение в существующем recovery без нового приёмника.

## Decision
Хранить continuation в существующем JSON checkpoint диалога: through, фиксированный верх окна, message after и признак неполноты. Каждая страница сохраняется целиком до cursor. Каждый вызов читает свежую голову, затем продолжает старый хвост; верх расширяется только при подтверждённом соединении. Отдельный sync lock сериализует scanner и ограниченный delivery refresh.

## Consequences
Старые checkpoint совместимы без миграции. После restart и исчерпания бюджета чтение продолжается, MID дедуплицируются. Равные timestamps не дают ранней остановки. Новая отделённая голова и недостоверные данные сохраняют gap. Все pages входят в прежний GET budget/deadline; invalid cursor перезапускает только диалог. Нужны регрессии и отдельная выкладка.

## Links
- .kiro/specs/inbound-recovery/requirements.md
- .kiro/specs/inbound-recovery/design.md
- .kiro/specs/inbound-recovery/tasks.md
