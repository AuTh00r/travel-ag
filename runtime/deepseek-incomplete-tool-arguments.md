---
status: verified-local
date: 2026-10-18
scope: diagnostic and bounded retry hardening; provider cause unresolved
evidence: tests/test_incomplete_tool_arguments.py
---

# Tool arguments обрываются после manager

Symptom: два production ответа deepseek-v4-flash заканчиваются на
`"manager": `, finish_reason=tool_calls, 277/231 output tokens при лимите2048.
Лог не обрезан. Запрос передан менеджерам, Telegram receipts подтверждены.

Investigation: исходное provider message сохраняется deepcopy до SDK parsing;
response_log_content берёт эту строку, без streaming merge/repair. Обрезка
в нашем extractor/logger и обычный token limit не объясняют наблюдение.
Nullable strict schema ранее дала 13 успешных реальных ответов; её виновность
не установлена. Beta/strict/named function/thinking.disabled соответствуют
https://api-docs.deepseek.com/guides/tool_calls/ . Внутренняя причина дефекта
генерации провайдера неизвестна.

Hardening: bounded JSON EOF классифицируется incomplete_tool_arguments,
исходник остаётся в приватном журнале. Один из прежних двух вызовов получает
доверенное напоминание заново заполнить оба значения и закрыть JSON, без
частичного ответа в prompt. Не подставлять manager=null и не отправлять reply
из неполного объекта. Повторный отказ сохраняет прежний fallback.
ValueError на длинном числе и RecursionError остаются на старом validator path.

Verification: 6 SDK/handler RED → GREEN, затем numeric ValueError RED → GREEN;
private journal reason/raw/privacy case. Полный pytest 1480 PASS, Ruff/diff и
независимое review PASS. HTTP, модель и отправки заменены заглушками; SDK реален.

Deployment: по отдельному «деплой» установлен совместный пакет4,
PID4136/29 SHA/health PASS. Installed EOF parser smoke PASS; env/credentials
сохранены, tool scopeall. Ручных model calls и отправок не выполнялось.

Limits: paid calls не запускались. Устранение обрывов на стороне
DeepSeek и эффективность нового напоминания на живых запросах не доказаны.
Схема, endpoint, max_tokens, предел двух вызовов и бизнес-контракт не менялись.
