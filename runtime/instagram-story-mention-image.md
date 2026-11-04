# Story mention как фото с типом источника

2026-10-09. Симптом: story_mention оставалось неизвестным вложением, хотя событие
имеет media URL. Требование владельца: обработать как фото, сохранив пометку типа.

Fix: image-like predicate принимает только image/story_mention; точный URL
передаётся прежнему prepare_images. image_types соответствует позиции images
при merge, prompt labels/system и история обозначают story mention. Обычный
вопрос не подменяется. 5-second collector, оригинальные bytes, guard/queue/
takeover и image-флаг сохранены. Mixed photo+mention объединяются; отдельные
post/story reply сохраняют identity. Mixed unsupported не даёт partial image set.

Verification: 15 focused mention tests PASS; full local 515 PASS/Ruff PASS;
read-only review без замечаний. Проверены parser/merge/type order/MID, отдельные
POST/5-second window, no-caption/flag-off, exact prompt/history, missing URL и
реальный MP4 validator отказ без AI. Server stage: 513 PASS/2 JPEG-artifact
skips/Ruff PASS. Backup-mention, 5 файлов applied/15 SHA verified, listener
11532 → 11672, local/public health ok. Live mention запрошен, ещё не проверен.

Границы: только JPEG/PNG; MP4/GIF/невалидный URL дают честный IMAGE fallback.
Живой Meta payload этим тестированием не подтверждён. Official docs research
blocked/no-research: story-mention страницы Meta вернули 429/inaccessible;
сторонние пересказы не использованы как официальное доказательство. Новая
реальная отправка владельца нужна для end-to-end проверки.
