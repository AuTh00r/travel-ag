---
status: verified
date: 2026-10-09
scope: Instagram Direct, Windows production, N1/N2/N1b
evidence: .kiro/specs/media-understanding/tasks.md
promoted_to: null
---

# Instagram phone-card и незакрытый служебный блок

## Симптом и причина

После номера и автоматической телефонной карточки клиент получил внутренний
`===МЕНЕДЖЕР===`. Regex требовал закрывающий маркер: незакрытый блок не извлекался
и не очищался. Template payload канал отбрасывал и относил к blind non-text.
Graph reread старого сообщения вернул is_unsupported без payload.

## Исследование и исправление

Marker extraction допускает EOF, cleanup удаляет также повреждённый header.
Пустой visible ответ получает нейтральное подтверждение. Старые assistant blocks
очищаются только в копии prompt; новые записи истории содержат visible ответ.
Notifier берёт подтверждённый input phone даже без model phone field.

Узкие contact/phone_number и generic Phone number со совпадающей телефонной
кнопкой нормализуются в текст. Phone-only postback требует видимого номера и MID.
Phone text/card в одном webhook сохраняют все MID. Auto-card после обычного
phone-only текста за 30 секунд не вызывает второй AI/notification; cache <=1024,
без подавления обычного повторного текста или нового вопроса. Story/referral
контекст и MID после shared merge сохраняются.

Первый live повтор опроверг предположение о flat generic: payload_keys=['generic'],
recognized_phone=false; два phone-only text/template POST с интервалом 0.8–1.4 с.
N1b поддерживает nested generic. Empty nested generic без текста/story/referral
и с единственным recent phone-only input коррелируется с подтверждённым текстом
и подавляется как служебная карточка. Номер из пустого payload не извлекается.
Unknown/nonempty/ambiguous шаблоны сохраняют прежнюю ветку. Диагностика выводит
имена полей, тип, количество элементов и boolean, без номера/payload/URL.

## Проверка

Marker red 6 FAIL/1 PASS → green; nested red 3 FAIL/4 PASS → green.
N1/N2 full local 449 PASS, server 447 PASS/2 JPEG-artifact skips, Ruff PASS.
N1b full local 457 PASS; server QA/guarded deploy описаны в tasks.md/rollout.md.
Первая параметризация webhook regression обнаружила общие MID между кейсами;
тест изолировал _processed_mids, повтор полного набора завершился 457 PASS.
Внешние отправки/AI mocked, отдельная test DB для каждого теста. Местный pytest
сначала получил PermissionError Windows temp; отдельный --basetemp дал green.
Ручных paid calls нет, старое сообщение не replayed.

N2c, 2026-10-09: владелец сообщил об older phone после отправки нового.
Safe DB comparison подтверждает latest phone-only normalized и новый canonical
номер, Telegram delivered/counter=1. Контакты уже берутся из current input, но
AI context/name либо prior mixed contact могли содержать старый номер.
Red 4 FAIL → детерминированный contact context/tag для любого current phone,
независимо от AI marker. Телефонные contact records не используются как query;
current question приоритетен. Старый номер в AI name также не допускается.
Read-only review нашёл greedy contact+budget/date; red 8 FAIL/4 PASS → known
canonical spans/BY local alias проверяются до общей валидации. International
'+' contact-like run не пропускается из-за соседних цифр. Даты/бюджет без
контакта сохраняются. Local final 478 PASS/Ruff PASS. Safe source logger хранит
лишь model_phone_present/model_phone_matches_input, без номеров/контекста.
Exact Telegram section старого номера не восстановлен; подтверждённый defect
воспроизведён тестом, no replay/manual send. Новый live повтор после N2c ожидается.
Final N2c: local 478 PASS, server 476 PASS/2 JPEG-artifact skips/Ruff PASS;
guarded backup-contact-source-v2, 14 SHA verified, health 200/ok. Review подтвердил
known phone span fix, 12 changed-contact regression cases green. Initial stage
до review correction не deployed, prod DB/history/limit в N2c не изменялись.

Live final, 2026-10-09 01:44 Минск: новый normalized phone отличается от всех
предыдущих; спустя 1.35 с actual payload.generic.elements=[] → empty_duplicate /
ignored_duplicate. Никакого второго AI/non-text processing/ответа. Model phone
absent в safe source log, значит actual current input взят кодом; Telegram sent
четырём configured recipients и один Instagram reply. Latest assistant 75 chars,
без service marker; counter 1→2, manager_last_at=null. Raw номера/payload/текст
уведомлений не читались в stdout, manual paid calls/replay/reset отсутствуют.
Verified для указанного empty-card/text order и current-phone source; полный
raw Telegram body не восстановлен, другие неизвестные template не считаются phone.

Live после N1b: в 22:15 UTC пришёл только phone-only text, без template; один
visible reply, marker отсутствует. Но AI не создал escalation, Telegram не вызван.
До этого владелец разрешил сброс только escalation_count/manager_last_at тестового
диалога; backup saved/history preserved, остальные клиенты не изменялись.
N2b до кода фиксирует этот отдельный root cause: подтверждённый current phone
запускает notifier независимо от AI marker, с прежним limit/takeover. Phone-only
ack короткий и соответствует success/error/limit. Red no-marker 3 FAIL → green.
Read-only review обнаружил, что no-marker question+card давал старый контекст.
После red 2 FAIL/7 PASS current question получил приоритет; phone-only использует
последний содержательный user запрос. Local final 466 PASS, server final
464 PASS/2 JPEG-artifact skips/Ruff PASS; 14 SHA verified, health 200/ok,
backups phone/phone-nested/phone-notify/phone-context. Final live повтор ожидается.

## Границы

N1b actual nested generic.elements=[] подтверждён live, fixed flow verified.
Исходный test dialog limit/takeover сброшен только
по явному разрешению владельца, с backup/history verification. Другие диалоги
не изменены. Normal limits/takeover в коде сохраняются.
Reverse order отдельных POST card → text не покрыт cache. Story mention/audio/
direct video не изменены. История/лимиты/настройки других клиентов сохранены.
docs_check.py/skills_validate.mjs отсутствуют в проекте; документация проверяется
git diff --check, факты — тестами и deployment manifest.
