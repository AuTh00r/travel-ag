---
status: verified
date: 2026-10-08
scope: Instagram native ig_reel webhook classification, shared media flag enabled
evidence: tests/test_shared_media.py; .kiro/specs/media-understanding/bugfix.md
promoted_to: .kiro/specs/media-understanding/design.md; docs/ARCHITECTURE.md
---

# Native Reels попадал в non-text вместо vision

## Симптом и причина

Живой отправленный Reels дал instagram.non_text.received с types=[ig_reel],
затем legacy non-text response; media preparation/vision не запускались.
_SHARED_POST_TYPES принимал только ig_post/share. Ошибка маршрута доказана
логом типа и regression: игнорируется источник без вопроса, при вопросе возникает
раздельный текстовый маршрут. Это не ошибка DeepSeek или video decoder.

## Исправление

Добавлен ig_reel с guard по shared_media_enabled, чтобы off сохранял прежнюю
ветку non-text. Поля ID/URL передаются existing Graph resolver; candidate
reel_video_id не считается автоматически равным Graph ID. Диагностика хранит
только тип, подтверждённый numeric candidate, имена известных identity fields
и наличие URL; без raw URL, подписи и содержимого webhook.

## Проверка и границы

До fix — 2 FAIL, после — 7 PASS; full local pytest 408 PASS/Ruff PASS.
Server pytest 406 PASS/2 JPEG-artifact skips/Ruff PASS. Guarded 2-file patch,
backup, 12 SHA совпали, local/public health 200/ok после нового процесса.
Повторная отправка владельцем подтверждает и live pipeline: ig_reel содержит
reel_video_id, exact Graph resolver дал полное видео, получены 10 кадров, один
vision завершён (32617 input/259 output), ответ отправлен Instagram за 14.4 с.
Из первого события payload не сохранён; автоматический replay не выполнен.
Этот успех не гарантирует доступ к любым чужим/приватным публикациям.
Meta docs новых вложений вернули 429: схема URL не объявляется гарантированной.
