---
status: verified
date: 2026-10-10
scope: Instagram bot, Python 3.12, existing Telegram manager fanout, Windows Server 2019
evidence: .kiro/specs/media-understanding/tasks.md N7; tests/test_handoff_receipt.py; tests/test_voice_messages.py; private handoff-applied.json
promoted_to: docs/ARCHITECTURE.md; .kiro/specs/media-understanding
---

# Неподтверждённая передача менеджеру

Symptom: после голосового про Сербию клиент получил «Я передал ваш контакт», но нового Telegram-уведомления не было. Тестовый аккаунт уже имел escalation_count=3; снятие manager takeover сохраняло этот счётчик.

Investigation: read-only проверка сессии подтвердила effective_count=3 и reset720hours. В текущем ответе отсутствовал действующий marker, поэтому notifier не вызывался. Это не потерянный Telegram request и не ошибка GigaAM. Предположение «модель должна сама правильно трактовать лимит» не обеспечивало поведение: prompt запрещал marker при лимите, но другие правила требовали фразы о передаче/обратном звонке. Code guard покрывал только phone-only acknowledgement. Дополнительно _send считал HTTP200 достаточным, а fanout объявлял общий сбой даже после доставки одному получателю.

Root cause: клиентская фраза модели не была связана с фактическим outcome уведомления. Противоречивые инструкции и предыдущие подтверждения в истории позволяли повторять неподтверждённое утверждение.

Fix: prompt отвечает по существу и формирует служебный marker при допустимой эскалации, но не подтверждает передачу. Main фиксирует none/sent/failed/limit, удаляет неподтверждённые утверждения/обещания передачи и обратного звонка из видимой части модели; полезный текст, ссылки, вопросы и контакты сохраняются. Программа добавляет проверенное подтверждение после отправки. При limit явно сообщает об отсутствии нового уведомления; при error сообщает, что подтвердить передачу не удалось, без ложного вывода о гарантированном отсутствии доставки. Voice/non-text fallback используют ту же честную семантику. Phone-only остаётся коротким.

Telegram _send проверяет HTTP200 + JSON ok is True, иначе sanitized TelegramError без token URL/body. Fanout продолжает все configured recipients; хотя бы одна подтверждённая доставка означает успех, partial failures дают warning. Если подтверждений нет — исключение; caller увеличивает count ровно один раз при успехе. Первичный источник: https://core.telegram.org/bots/api#making-requests .

Verification: initial red22FAIL/1PASS; дополнительные review red6FAIL, затем2FAIL для «ложное подтверждение + вопрос»; все38handoff regressions после fix PASS. Две voice regressions покрывают failure-at-limit и recognized voice с past confirmation/count3. Финальный полный pytest754PASS/8existingwarnings, Ruff/diff-checkPASS, независимый read-only review без существенных дефектов. Проверены partial-before/after/all-fail, invalid JSON/ok/transport credential redaction, count/history, no marker/broken marker, mixed phone, useful clause/URL/question/footer.

Deployment: только main.py, prompts.py, telegram_notify.py. Начальный guard остановился до замены production source: notifier отсутствовал в прежнем20-entry manifest. Read-only повтор подтвердил прежние SHA/PID/health; notifier отдельно pinned SHA, backup guard исправлен и повторён до green. Source+manifest backup-v2 verified; manifest расширен до21entries, .env/launcher неизменны, listener14396→2416; local/publichealthok. Actual deployed source proof проверил4reply outcomes,2API receipts и partial fanout с mock AI/network/send/DB; реальных внешних сообщений, paid AI calls и production DB writes нет. Напечатанный escalation.notify_failed для proof-client — ожидаемый negative test, не ошибка текущего клиента.

Local manifest: remote копия сохранена отдельным evidence artifact; diff ограничен двумя изменёнными source entries и добавлением notifier. Локальная резервная копия проверена, только эти entries изменены. Не заменять канонический manifest вслепую. Rollback helper восстанавливает проверенные source/manifest backups и вызывает прежнюю scheduled restart задачу; откат не понадобился.

Portability limits: подтверждение Telegram означает принятие API сообщения минимум в один configured chat, не прочтение менеджером. Timeout может наступить после доставки, поэтому failure wording осторожное. LLM prose guard распознаёт покрытые русские формы, это не математическая гарантия для произвольного языка/перефразирования; prompt остаётся первой линией. При изменении языка или шаблонов добавить meaningful regression. Лимит3/reset720hours и история/пауза клиентов не сбрасывались. Нового live owner message после этого rollout пока нет; deployed mocked proof не выдаётся за реальную клиентскую отправку.

Documentation tooling: referenced global runtime template и AGGG4 docs_check/skills_validate отсутствуют в этом репозитории; metadata/sections использованы из прочитанного runtime-knowledge skill. Проверки этих отсутствующих инструментов не выдаются за пройденные; repository pytest/Ruff/diff выполнены.
