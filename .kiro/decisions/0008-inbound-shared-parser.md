# 0008. Inbound Shared Parser

## Status
accepted

## Context
Две независимые классификации API и webhook расходились: template исчезал, story reaction вызывала модель, фото и следующий вопрос разделялись. Альтернатива отдельных исправлений сохраняет дублирующиеся правила.

## Decision
API преобразует только подтвержденные поля в общую форму сообщения. Один синхронный parser и общий media merge используются webhook и recovery, включая смешанные источники; служебная неполнота остается метаданными.

## Consequences
Нужна parity матрица всех поддерживаемых маршрутов, сохранение сюжетной привязки и корректная переклассификация поздних webhook. Отсутствующее API медиа этим не восстанавливается; независимый прием событий требует отдельного согласования.

## Links
- .kiro/specs/inbound-recovery/requirements.md
- .kiro/specs/inbound-recovery/design.md
- tests/test_recovery_parity.py
