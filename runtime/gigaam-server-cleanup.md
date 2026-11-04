# Очистка испытаний STT: оставлен GigaAM

2026-10-10. Владелец явно выбрал GigaAM и разрешил полностью удалить с сервера остальные испытанные движки распознавания. Очистка выполнена в изолированных каталогах испытаний; распознавание голосовых в production пока не включено.

| Было | Стало | Проверка |
| --- | --- | --- |
| Whisper small/medium/large-v3-turbo, отдельный Python runtime и model cache | Удалены модели, окружение, логи и скрипты испытаний | Все разрешённые targets отсутствуют |
| Parakeet Q8, portable runtime, ZIP, тестовые файлы | Удалены с сервера | Каталог и отдельные helpers отсутствуют |
| faster-whisper/CTranslate2 install cache | Удалены 8 подтверждённых wheel/metadata/cache-header файлов | Повторный scan ZIP METADATA/PEP metadata/package JSON: exclusive STT entries отсутствуют |
| Mixed multi-engine benchmark helper и Parakeet/Turbo результаты в GigaAM trial directory | Удалены с сервера | Target absence; private evidence проверены локально |
| GigaAM модель/окружение/аудио/результаты | Сохранены | Protected SHA unchanged, pip check PASS; offline Instagram voice и silence smoke PASS |
| Бот, конфигурация, launcher и исходные собственные аудио | Сохранены без перезапуска | 17 deployed SHA + launcher/.env/requirements, PID2984, local/public health ok |

Удалено 27 targets и 8 отдельных записей кэша; логический размер файлов **4 700 191 930 байт (4,70 GB / 4,38 GiB)**. Это сумма размеров удалённых файлов, а не гарантированный прирост свободного места: remote PowerShell PSDrive.Free недоступен. Общие пакеты/кэши, действующая embedding-модель и production Torch/ONNX не удалялись.

Перед удалением проверены абсолютные разрешённые границы, inventory/size и отсутствие reparse points/активных trial processes. Частные результаты снятых движков (27 файлов) перенесены на компьютер владельца и проверены по SHA; веса не архивировались. SHA экспортированного архива:97C1F2F4182E7229981029E392D950B41DC24120E3B86C2C4BE09B50C45049D2. После подтверждения локального экспорта промежуточные серверные архив/копии результатов также удалены. Historical comparison reports сохраняются локально.

Полная pre/post проверка 6582 protected SHA PASS:6560 файлов сохранённого GigaAM trial,20 production файлов (включая17 deployed manifest),2 исходные записи. Read-only review подтвердил отсутствие пересечений разрешённых targets с protected files и отсутствие generic cache purge. Проверка всех существующих промежуточных предков удалённых targets/cache records также PASS (reparse points отсутствуют).

Во время подготовки исправлены ошибки транспортного размера SSH-команды и PowerShell5 сериализации JSON-массива cache (`value`/`Count`); destructive preflight остановился до удаления и повторён до PASS. После удаления новый smoke helper сначала передал int16 и получил onnx-asr WrongDataTypeError; исправлен на normalized float32, повтор тех же voice/silence проверок PASS. Верификация продолжена отдельным verification-only helper, удаление не повторялось. ONNX Runtime предупреждение о Windows Server2019 сохранилось: успешный smoke не означает официальную поддержку ОС.

GigaAM smoke: onnx-asr0.12.0/ORT1.23.2, CPU2intra/1inter/no-spin, local verified FP32 model, без сети и DeepSeek/Instagram sends. Результат: собственное сохранённое голосовое распознано (42символа, без вывода текста), тишина пустая. Процесс smoke завершён; остаются обычные production Python PID2984/14312. V1d интеграция голосовых остаётся незавершённой.
