---
status: verified
date: 2026-10-18
scope: local temporary SQLite and mocked providers
evidence: tests/test_recovery_manager_pause.py
---

# Пауза менеджера ошибочно расходует технические повторы

Symptom: recovery job с активной manager pause проходит два
fresh_context_unavailable и завершается failed_final/session_or_source_changed.
Read-only production snapshot: source versions 1/1, manager_active=true,
result отсутствует, новых уведомлений по задаче нет.

Root cause: can_resume вызывался до проверки manager pause. При False и
последней попытке final_failure обращался к context.get_session, получал
StaleWork из-за менеджера; внешний catch записывал технический отказ.

Fix: guard state/claim/pause перед can_resume и сразу после await, также
перед retry в StaleWork catch. Активный менеджер отменяет принадлежащую
worker processing-задачу. Изменившийся owner/state останавливает старую
обработку без записи; finish сохраняет assert_claim/version/lease checks.

Verification: 9 RED/4 исходных PASS → 13 GREEN; ещё 5 state/owner guards.
Полный pytest 1480 PASS/8 прежних warnings, Ruff/diff/read-only review PASS.
Снятие паузы не возрождает cancelled; обычный gap без менеджера сохраняет
technical retry. Спека inbound-recovery, TSK-022/FR-17/AC-37..39.

Deployment: по отдельному «деплой» 2026-10-18 установлен совместный пакет4,
PID4136/29 SHA/health PASS. Env/baseline/тестовая сессия сохранены, БД не
заменялась. Offline rollback сохраняет новые receipts/unknown; scope allowlist/1.

Limits: ранее завершённая failed_final задача не
мигрируется и не переигрывается; паузы/лимиты/история не сбрасываются.
