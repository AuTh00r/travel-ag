---
status: verified
date: 2026-10-08
scope: Windows WinRT MediaComposition, Instagram MP4/H264 Reels
evidence: tests/test_shared_media.py; workspace artifacts reel-preparation-check/evidence.json
promoted_to: .kiro/specs/media-understanding/design.md; docs/ARCHITECTURE.md
---

# Последний кадр Reels при более длинной аудиодорожке

## Симптом

prepare_shared_media собственного Reels завершился decode_failed: вместо десяти
кадров получено девять, попытка последнего кадра завершилась ошибкой WinRT.

## Проверка причины

Полный MP4 загружен: 2 717 655 байт, H264/avc1 и mp4a. Гипотеза отсутствия
поддержки HEVC/AV1 не подтвердилась: этих кодеков в проверенном ролике нет.
Повторный native decode воспроизвёл ошибку. Video duration 8.533333 с,
audio duration 8.658186 с, Windows OriginalDuration округлена до 8.659 с.

## Причина

Последняя временная точка вычислялась по общей длительности клипа и попадала
за конец видеодорожки. WinRT GetThumbnail не извлекал кадр в этой точке.

## Исправление

src/services/story_media.py читает mdhd только у MP4 trak с hdlr=vide.
Проверенная числовая длительность передаётся декодеру через временный
video-timing.json; decode_story_media.ps1 использует минимум этой длительности
и OriginalDuration. Последняя точка отступает на один кадр. Звук не извлекается.
Для контейнера без доступного video timing сохраняется native fallback.

## Подтверждение

Повторный prepare_shared_media на том же Reels: десять кадров, первый 0.000 с,
последний 8.500 с; платных AI-вызовов ноль. Регрессионный тест проверяет выбор
video mdhd вместо более длинной audio track. Полный pytest: 403 PASS,
Ruff: PASS. Временные файлы удаляются и при ошибках/отмене.

## Границы

Проверено локально на одном реальном H264 MP4 и fixtures; это не доказательство
поддержки любого кодека/контейнера. Live shared webhook и ответ клиенту через
production пока не проверены. После деплоя native decoder на сервере подтвердил
VIDEO/IMAGE/VIDEO → 21 изображение на синтетических MP4/PNG, без AI.
Длинные, повреждённые и недоступные медиа дают
честное уточнение вместо анализа обложки или частичного набора.
