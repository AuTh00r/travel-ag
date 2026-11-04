# Пустой template после текста вызывает вторую эскалацию

2026-10-09. Источник: реальный incident screenshot + read-only безопасные логи,
synthetic async webhook regressions. Raw payload/номера/тексты клиентов не хранятся.

Симптом: обычное сообщение с номером в тексте эскалировано корректно, затем
отдельный template дал Non-text уведомление. Логи 11:04 UTC показывают интервал
1,16 с, generic.elements=[] / recognized_phone=false и две рассылки.

Причина: 30-second cache заполнялся только phone-only input. Ранее 5-second
ожидание в fallback откладывало client ack, но Telegram отправлялся до ожидания.
Эти две эвристики не обеспечивали единый пакет входящих событий.

Fix: после signature + MID reservation одно фиксированное окно 5 секунд на
sender, до любых пользовательских обработчиков. Stateless merge текущего
пакета, текст по порядку; empty generic с текстом удаляется с сохранением MID.
Реальная contact-card нормализуется строгим parser. Кеш предыдущих номеров,
user_contact_duplicate и AI timestamp suppression удалены. Manager echo
немедленный; он отменяет ожидающий пакет, error fallback учитывает takeover.
Пакеты сериализованы; следующий пакет может собираться во время текущего AI.

Verification: full local 500 PASS, Ruff/diff check PASS. Отдельные POST в обоих
порядках, phone-only/general text, MID retry, sender isolation, late template,
manager cancellation, sequential slow AI, exact image/Reel/story metadata;
настоящее окно >=5 с и немедленный HTTP 200. Даты/бюджеты отдельной строкой не
становятся телефонами; последняя явная phone строка побеждает старый marker.
Read-only review подтвердил устранение трёх замечаний. Server stage: 498 PASS/2
JPEG-artifact skips/Ruff PASS; backup-batch, 8 файлов применены, 15 SHA verified,
listener 3964 → 11532, local/public health ok. Live повтор запрошен, ещё не проверен.

Границы: empty generic без текста в том же окне сохраняет fallback; поздняя
карточка не сопоставляется с историей. Коллектор in-memory одного worker,
как существующая MID dedup. Истории разных ID остаются раздельными.
