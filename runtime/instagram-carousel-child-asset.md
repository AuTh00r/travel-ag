---
status: verified
date: 2026-10-09
scope: own Instagram Graph v25 media, URL-derived child assets; Windows PowerShell JPEG validation
evidence: tests/test_shared_media.py; .kiro/specs/media-understanding/bugfix.md
promoted_to: .kiro/specs/media-understanding/design.md
---

# Child asset не находил полную карусель; JPEG проверялся слишком долго

## Симптом и исследование

Live share с URL без явного ID вернул post_unavailable до vision. Conversation
API reread: is_unsupported=true, без attachments/shares; исходный URL неизвестен.
Permalink владельца доступен: CAROUSEL_ALBUM, 5 IMAGE/2 VIDEO, все 7 children.
Отдельные реальные native/Graph ID seventh child не находились старым resolver.
Это подтверждённый пробел, связь с первоначальным webhook требует live repeat.

## Причина и исправление

Поиск own /media сопоставлял только parent id/ig_id. URL-derived asset_id теперь
ищется и в children{id,ig_id}; полный parent повторно подтверждает принадлежность
child. Direct IMAGE/VIDEO от asset не объявляется всей публикацией. Explicit
Reel ID путь, три страницы, совместные identity guards и ограничения сохранены.
Логируются numeric candidate/source kind и хэш shortcode, без URL/payload.

В IMAGE decoder DetachPixelData() | Out-Null перечислял каждый pixel byte.
[void] сохраняет чтение/валидацию пикселей и убирает дорогой pipeline.

## Проверка

7 regressions FAIL до, 8 PASS после, включая direct IMAGE/VIDEO и отказы при
foreign leaf/несовпадении parent/child/type. Shared 38 PASS. Server full pytest
414 PASS/2 JPEG-artifact skips, Ruff PASS. Оба реальные child ID → exact parent
с 7 children. Та же native карусель: 25 original изображений за 12.562 с вместо
79.594 с; IMAGE decode 0.4–0.5 с, без paid AI. Guarded 3-file patch с backup,
12 SHA verified, restart и health ok, media flags true. Live repeat ожидается.

## Границы

Не гарантирует доступ к foreign/private posts, поиск за третьей страницей или
поддержку любой формы URL. Не заменяет thumbnail полным видео, не урезает carousel
и не меняет лимиты. Сокращение времени измерено на одной конкретной карусели.
