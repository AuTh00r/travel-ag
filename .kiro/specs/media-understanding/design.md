# Design: ответы на собственные истории (Quick Spec)

## Quick N42 design (2026-11-03, до кода)

ProviderResponseError на границе _ResponseModel вместо duck-typed model_dump:
принимать dict/SDK ChatCompletion, неверный тип/choices дают безопасный код
и bounded response_type. Остальные ошибки преобразования не маскировать.
Primary-loop использует внешний asyncio.wait_for всей ainvoke плюс прежние
сетевые120/120/240. Измерять monotonic elapsed_ms, отличать call_deadline от
provider_error. Отменяемый async HTTP завершается до retry; CancelledError
не ловится except Exception. Persisted budget, failed_final и outbox прежние.
Deadline включает всю async попытку; после него ждём очистки отменённого
HTTP. Блокирующий локальный код/подавление отмены принудительно не убиваются.
technical_context меняет только технический текст: причина/запрос/действие,
затем безопасные коды, попытки, длительность и ID. Исторический job не replay.
Для ошибок обработчика не утверждать, что отправки не было: мог упасть
save_session после legacy-доставки. Просить проверить переписку перед ответом.

## Quick N41 design

Recognize exact unsupported_type attachment in the same pre-media routing stage as
story_mention. Reuse the silent handoff barrier and handler with a distinct reason,
accurate neutral manager context and history provenance. Existing separately sent
messages remain independent; do not claim all such attachments are coauthor invites.
API normalization preserves an explicit unsupported_type before MIME-based GIF
filtering; unknown API content/flags do not manufacture this exact type. Username
lookup is optional: failure falls back to the numeric client ID. StaleWork from
profile/notification/session gates propagates to recovery without finalizing stale
work or sending a client reply.

## Quick N40 design (2026-10-31, до кода)

Primary invocation owns one bounded three-attempt series; timeout is supplied
by the120s factory for attempts1/2 and a240s per-invocation override for attempt3,
without mutating shared clients or SDK auto-retries. These are transport timeouts,
not a promised maximum wall-clock duration for the entire handler.
Validate and log each response; retry supported format failures using the existing
trusted reminder. Log exceptions at their actual stage, never raw exception text.
Check manager takeover between attempts and before planning the final notification.

On exhaustion, terminate as failed_final (not technical_retry). A dedicated silent
technical handoff records bounded sanitized attempt summaries with correlation ID,
retains the user's history and plans only Telegram delivery. Reuse the existing
durable notification operations keyed by source MID/job for ordinary and recovery
paths. Technical delivery does not consume the business consultation quota.
Recovery final_failure clears all client replies and includes safe failure reason.
No model calls for delivery retries; unknown results remain held for reconciliation.

Additive SQLite migrations: manager_tasks.kind (defaultconsultation) and
inbound_jobs.model_attempts/model_attempt_log (default0/[]). Reservation and its
safe pending log entry are committed before network I/O; completion replaces that
entry with bounded stage/reason/error type/status/origin/request ID. A crash consumes
the reservation conservatively and never claims that the HTTP call completed.
Only first semantic_wait transition resets this generation budget/log.
Technical task keys use technical: prefix and Telegram part1, preserving already
committed consultation part0. They are excluded from reviewer candidates and quota
increments; manager takeover closes both task kinds. error_only final results
permit Telegram diagnostics during Meta refresh failure, retaining delivery gates.


## Quick N38 design (2026-10-29, before code)

Keep deepseek-responses.jsonl and its response envelope stable. Add a private
deepseek-trace.jsonl using the existing safe rotating-handler/redaction utilities,
plus explicit recursive serialization of supported primitives/messages/media.
Unknown objects are omitted without repr; cycles/depth/collection/text/encoded-byte
bounds are explicit. Media blocks/data URLs are omitted as a whole, not regex
fragments; signed URLs/secret fields are sanitized before any length cutoff.

Diagnostic-only ContextVars bracket dispatch, model processing and delivery.
Use existing IDs to connect later workers: source MID hashes link input/grouping;
request/parent link model attempts/review; job/task/delivery/pending IDs link
plans and deferred sends. No new persistence identity or replay mechanism.

Write normalized inbound, model_request, model_response/error, proposal/review,
application decision, final_reply, notification_plan, delivery_started,
provider_result and receipt_recorded/commit_failed events. Actual call_messages
and review_messages are captured before each call, not reconstructed later.
The existing response logger also mirrors its already-sanitized record to trace.
Finalization is logged after handoff/limit decisions, including recovery's later
finalizer. Required routes and manager pauses emit outcomes without extra calls.
Transport traces never claim durable delivery before receipt commit succeeds.

One best-effort writer with bounded JSONL records (512KiB encoded) and20MiB×8
files keeps diagnostics bounded. Writer failure reports only a fixed safe marker;
no input, error body, credential, client or media dump reaches ordinary logs.
Automatic tests isolate both paths; offline semantic tests and paid budgets
remain unchanged. No deployment is part of N38.

## Quick N37 design (2026-10-29, before implementation)

Keep primary prepare_response unchanged. A dedicated review model sees the exact
catalog/question/history, the untrusted candidate and this client's open manager
tasks; its one internal review_handoff tool returns action, optional task ID and
the final reply/manager pair. This operational metadata is not a second customer
response format. Validate every field and task reference locally. Failure/timeout
retains the original valid response; cancellation propagates. Recheck takeover
after the new await before planning any sends. Required routes bypass the review.

Store task identity/revision/counting separately from session JSON to avoid stale
session saves overwriting receipts. Extend the existing delivery journal with
task/operation/target/version metadata. New tasks send; updates edit confirmed IDs
per destination, sending only to destinations known not to have received the task.
Unknown intents never create replacement notifications. Recovery commits task
changes and notification drafts atomically; the legacy path also persists intent
before HTTP. Count the first confirmed new task once, not edits or delivery parts.
Manager cancellation closes tasks and cancels unsent operations without erasing
receipts for HTTP already in flight. Task references expire with the existing
escalation-reset window; unrelated new questions stay independent.

The ledger covers ordinary model consultations. Required contact/feedback/media
routes preserve their existing dispatch and counting. Source identities are
job IDs or webhook MIDs; manager_task_changes deduplicates replay, including
legacy NULL job_id. A unique task/revision/destination index protects SQLite NULL
semantics. The legacy retry worker shares the business client lock and processes
only known-unsent operations of the current open version. Sending at restart
becomes unknown. Recovery retains its existing scope; no expansion is implied.
Known receipt writers advance delivery-job session revisions through the existing
_write_own_session; they do not masquerade as manager takeovers. Processing CAS
still rejects stale drafts. Open-task receipts are exempt from generic cleanup.

Live correction: compose the dedicated review system with the same trusted
primary business, security, link/action and closing blocks. Exclude primary
prepare_response/JSON transport instructions and dynamic escalation-limit wording.
Specific review rules retain unsupported already-specified periods, distinguish
catalog facts from client choices and preserve the exact unresolved question and
unambiguous known trip context. See n37-review-bugfix.md; original expectations
are not weakened to match the first run.

Telegram uses editMessageText with saved chat_id/message_id; mismatched receipts
are unknown and edit errors never fall back to sendMessage. Official reference:
https://core.telegram.org/bots/api#editmessagetext . Accepted architecture:
.kiro/decisions/0017-reviewed-manager-tasks.md.

Generate catalog diagnostics from captured tours_text immediately before the
primary call and pass that same immutable metadata to the review journal. Keep
secondary calls distinguishable by phase/parent ID. Test network effects with
stubs; prepare an anonymized 21-case semantic evaluation without executing paid
calls. Record architectural choices through decisions.mjs before implementation.

Release preparation and live-evaluation boundaries: n37-release.md. The evaluator
defaults to dry-run, reserves/fsyncs each call, stops on an unconfirmed review and
rejects report reuse, excessive budgets and stale catalogs for date regressions.

## Micro N36 design (2026-10-26)

Use the same _MANAGER_DECISION_RULES in normal and limit escalation blocks; refine
the old subjective-uncertainty/catalog no-fit rules and limit wording.
Explicit handoff/contacts/complaints and required special routes outrank the
resolved-question rule. For ordinary consultation a specific unanswered question
is needed; declining the original tour does not imply no suitable alternatives.
Keep the existing manager schema and dispatcher; improve context itself as the
human-readable reason, without a separate decision call or a reason field. Specify
who performs the task: company-service questions are for the manager to verify;
the customer can clarify their own preferences/missing personal details.
These are tasks described in manager.context, not an extension of the bot's own
clarifying-question permissions; the existing BASE rule for those is retained.
Record six synthetic cases for a bounded standalone model evaluation. Production
network sends and session stores are absent from that runner; actual calls remain
permission-gated. Ordinary offline tests prove protocol/priority construction and
preserve existing delivery guards; do not claim they determine model behavior.

## Micro N35 design (2026-10-22, до кода)

Supersede automatic ad-analysis routes including N34 for actual ADS input. Normalize
ADS events to ordinary typed text before grouping and at dispatch/processing for
old persisted queues; retain routing identities but drop contextual/media fields.
Empty ADS becomes ignored. Normalize before any story-hint enrichment and do not
infer a new story from an ad response. Ordinary events retain existing routes.
Recovery uses the same normalization and must not restore ADS silent permission.
No history migration or data deletion; do not add new ad context to prompt/history.
Known historical automatic ad annotations are stripped from a copied prompt-history
projection, never from stored entries. Single-MID API/webhook enrichment already
replaces the old payload with the richer webhook rather than unioning media keys;
retain this behavior and verify both source orders. Keep the private batch marker
separate from source detection so independent customer media are not stripped.

## Micro N34 design (2026-10-20, до кода)

Remove blanket feed rejection only for PLACEMENT. Existing exact ad/account and
creative identity plus effective/source Instagram permalink checks still bind the
canonical source. Request full creative fields expanded on the exact ad, retaining
legacy direct lookup only for an ID-only creative reference. This preserves the
ad-context Instagram permalink actually absent from direct creative GET in live
proof. Resolver attaches internal _ad_source=marketing_variant; shared
preparation carries it into StoryMedia.ad_source. Ad preparation retains that
provenance and optionally appends validated clicked images, with distinct labels
and a caption warning about unconfirmed displayed variant. Availability failures
of either unsupported feed or clicked image retain existing available sources;
security/format/size failures remain terminal. Never interpret rule order or
ad_title as a placement selector. Aggregate provenance conservatively; main labels
and history distinguish canonical variant from exact and clicked-only sources.
Official reference: https://developers.facebook.com/docs/marketing-api/dynamic-creative/placement-asset-customization/

## Micro N33 design: EOF tool arguments

См. bugfix.md до реализации. После проверки envelope response_arguments лишь
диагностирует JSONDecodeError на EOF для непустой строки <=16000 символов;
остальные ошибки и данные остаются на прежней проверке, ValueError/RecursionError
не превращаются в provider exception. Raw message не изменяется. Новый reason
в TOOL_RESPONSE_ERRORS наследуется allowlist журнала и format retries. Prompt
добавляет фиксированное напоминание полного объекта, без исходных аргументов.
Никакого JSON repair или замены nullable schema. ADR0009/0005 сохраняются.

## Quick V1 design: isolated Whisper trial (2026-10-10, до кода)

GigaAM design before implementation: dedicated trial helper directory/venv/cache; official GigaAM-v3-e2e-rnnt with CPU or validated ONNX conversion, pin upstream revisions and artifact SHA, inspect inference implementation before installation/use. Reuse existing canonical WAV/PCM SHA for3 baseline cases and external Windows kernel+user/WorkingSet counters. Explicit2 intra-op/1 inter-op threads,1request, environment thread limits before numerical imports. Load model once and consume complete results per first+two warm passes. Prefer existing PyAV audio decoder, no system FFmpeg/PATH changes. Standard official transcribe≤25s; a bounded lossless chunk path must be separate and tested with owner audio joined to>25s, clearly disclose boundary risks/changed runtime behavior. If an installed offline Russian TTS voice exists, synthetic number/date/name control may supplement actual owner audio; otherwise request existing sample path while progressing baseline trial. Do not substitute an earlier mismatched text for a literal reference or invent universal WER. Keep transcripts private, sanitize errors, checkpoint eachcase, no prod source/config/launch edits; baseline and final17manifestSHA/launcher/listener/local+publichealth must match. Comparison remains experimental, not production architecture selection; decisions CLI absent as previously established.

GigaAM CPU-scope refinement before second run: initial explicit2threads produced process CPU16..25% of16logical capacity. ONNX has separate encoder/decoder/joint sessions with worker spinning enabled by default; official threading docs provide session.intra_op.allow_spinning=0 and session.inter_op.allow_spinning=0. Preserve first report unchanged and trial identical files/repeats in separately tagged no-spin report; compare measured latency/CPU/transcripts rather than assume a cause or a hard global2-thread cap. No changes to model precision/audio/decoding; use no-spin figures as candidate only if empirical comparison supports it. Source: https://onnxruntime.ai/docs/performance/tune-performance/threading.html .

GigaAM actual result: pinned community ONNX FP32 revision322c3b29492673eb7d0b434bfa9dfb8653e34d02,5files892410829bytes SHAverified; separate onnx-asr0.12.0/onnxruntime1.23.2/numpy2.2.6, noTorch/HFremote-code. Shared canonicalbaseline and deterministic RMS200ms17..23s chunks for joined43.127s/TTS45.39s, full sample coverage PASS; this simple slicing can truncate words and is not accepted productionlongform. Default/no-spin30passes textidentical; numericfields/tournames preserved byGigaAM; no-spinCPU~12.4% but CPU-seconds18..38%more vsdefault. Wholeverifier78recordsPASS, read-onlyreview/input/modelchecksPASS, final17SHA/launcher/PID/local+publichealth unchanged, alltrialprocesses exited. RuntimeOSwarning WindowsServer2019 retained; successfulrun !=vendorOSsupport. Detailedscope/latency/RAM/CPU/quality in runtime/gigaam-whisper-parakeet-comparison.md; V1d remainspending.

Parakeet comparison design before code: portable official NVIDIA NeMo-Speech.cpp Windowsx86_64 CPU release in a unique helper directory, verify published SHA256 and model artifact provenance; no installer PATH/system/prod modifications. Official Parakeetv3 Q8 GGUF, existing isolated PyAV decoder converts both actual owner files to identical16kHz mono PCM16 WAV shared by engines. Start with CLI capabilities/version/help and explicit cpu backend/2threads/one request; use persistent benchmark/HTTP engine if available to separate cached model load/first inference/warm inference. External Windows process counters include native threads/peak working set; always distinguish total process CPU/latency from inference-only timing. Reuse existing Whisper small/medium/turbo locally installed caches/settings and remeasure same decoded audio/2 repeats; keep earlier original-M4A measurements separately. Silence case and private raw text permit honest manual comparison; no supplied earlier mismatched text as reference. Source17 hashes/launcher/health checked before/after, no bot restart needed. No production architecture chosen; decisions CLI absent and comparison is experimental.

Parakeet comparison result: official0.2.0 CPU runtime/checksum and714MB Q8 LFS checksum verified. Resident127.0.0.1 HTTP/one worker/noVAD measured against faster-whisper1.2.1 CPU INT8/VAD/beam5.36 runs, identical16kHz PCM proven by SHA, all repeated texts stable and silence empty. Per-run CPU kernel+user/elapsed/16 independently verified using stored precision rounding bounds; peak process working set distinct from two post-run snapshots, not average RAM over execution. Parakeet HTTP/WAV overhead and native-only memory vs Python Whisper scope explicitly documented; cached readiness/load timings not identical cold-start scope. Full benchmark/report: runtime/parakeet-whisper-comparison.md. Temporary native process exited; production17hash/launcher/listener/health unchanged. V1d must define decoder/queue/lifecycle before integration; no service enabled by this trial.

Native download result: authorized temporary wrapper captured one new own-account signed audio webhook; URL present, CDN200/36384bytes/MIME video/mp4. File signature MP4/isom, one audio stream AAC48000Hz/stereo, duration6.912s; isolated PyAV16.1.0 fully decodes162frames. Preserve byte-based inspection and audio-stream detection: do not reject voice solely because CDN MIME is video/mp4. Old message Graph attachments empty does not imply incoming webhook lacks URL. Wrapper explicitly sets production CWD before import. Original launcher restored after download with second authorized restart;17 source hashes unchanged and local/public health ok. No model transcription in this probe. Future integration must retain voice URL internally before current parser discards it, validate CDN redirects/size/time, and use existing decode path; concrete limits/provider integration remain V1d.

Download feasibility probe before code: user explicitly asks whether incoming Instagram voices are downloadable and actual format. Inspect own test sender2037820643484263 audio events only; no other customer data/text/URLs printed. If existing event available, read message attachments via authenticated Graph GET; media CDN URL in memory only, validate existing HTTPS allowlist per redirect, streamed download≤10MiB/timeout, inspect real bytes/container/audio codec using isolated PyAV (not filename). Otherwise require a fresh owner Instagram voice for end-to-end proof. Helpers isolated outside production; no processing/send/reset/deployment/STT external APIs. Official Meta sample includes audio attachment payload.url but does not establish voice encoding: https://github.com/fbsamples/messenger-platform-samples/blob/main/postman/instagram-platform-api.postman_collection.json .

Live discovery: fresh own audio webhook logged, but Graph GET matching MID/id/from succeeds200 with no attachments; its /attachments edge succeeds200/data empty. Cannot recover discarded URL from that message. Prepare isolated temporary ASGI wrapper: imports unchanged src.main/app, wraps existing instagram.receive_message only after signature verification, captures once own sender's audio payload.url for≤10minutes, existing parser always called unchanged. One bounded background download (HTTPS CDN allowlist each redirect,10MiB/45s, no Graph token to CDN), private audio artifact and sanitized metadata only. No new endpoint/env/dependency/source edits in production; use existing app ports/config. Requires separate authorization to switch production runtime temporarily, then restore normal launcher after proof; prior local Whisper trial does not itself authorize this diagnostic restart. Validate wrapper with synthetic malformed/other-user/echo/URL/duplicate/delegation/download cases before asking. No manual replies, session reset or STT API call.

CPU measurement extension before code (owner asks server load): repeat identical turbo sample twice, measure process CPU-seconds via time.process_time across fully consumed STT, divide by actual wall time and os.cpu_count to report average share of total logical CPU capacity. Include native worker CPU time; exclude model load/decode/imports. This is per-process averaged STT CPU, not system-wide CPU or instantaneous peak. Preserve new report separately from baseline; production unchanged.

Trial extension before implementation: same owner M4A21.439s, compare small and medium CPU/INT8/2threads/beam5 without initial_prompt or supplied reference hints. Preserve each model's private transcript/report separately; one first transcription and one same-process repeat measure warmed latency. The earlier pasted text is not an accuracy reference for this different file (owner confirmed). Pin PyAV16.1.0 with faster-whisper1.2.1: PyAV19.0.1 rejects metadata_errors in real decode. Accuracy review remains explicit, no percentage without literal reference and no dates/phone claim on a sample without them.

Second trial extension before code: medium STT17.240/16.273s,1,767.1MiB, first phrase missing noun («Меня интересует в Варшаву»). Compare supported turbo (faster-whisper1.2.1 official model map → mobiuslabsgmbh, now Dropbox, converted OpenAI large-v3-turbo) with identical CPU/INT8/2threads/beam5/VAD and2 repeats. Record audio SHA/decode time/private transcripts for each repeat; same-process repetition still excludes initial model loading. This is bounded model evaluation, not automatic production choice. Sources: https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/faster_whisper/utils.py ; https://huggingface.co/openai/whisper-large-v3-turbo ; https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo .

Owner chooses local Whisper before integration. First step: separate voice-trial environment in deployment helper directory, separate model cache, official faster-whisper package and Systran/faster-whisper-small model. Use CPU/INT8,2 threads,1 worker, beam5, Russian language, VAD. Load model before measuring; collect actual segments (generator is lazy), report cold load plus warmed STT wall time/audio duration/peak working set. Local audio only (WAV/MP3/M4A/OGG), validate≤10MiB/180seconds before STT; no AI/Graph/client/manager calls. Zero-filled WAV is only empty-speech smoke, not a Russian accuracy claim. Actual sample/expected words supplied by owner; compare named tours/dates/numbers literally, uncertain contact requests confirmation. User audio report is private and no transcript is printed to service logs.

Integration design after trial success: preserve audio URL and MID separately from visuals, ordered voice-aware five-second merge must combine transcript+texts+other media into one final DeepSeek call. Decode/download guard shared in intent but AUDIO needs own MIME/container branch; never use VIDEO decoder for voices. STT between existing user guard/takeover and FAQ/prompt, check full transcript input afterward and takeover before send. Unknown speech remains honest clarification. No new service enabled until trial meets practical latency/quality. Existing decisions CLI absent; this is trial selection, not settled production architecture.

## Micro N6 design (2026-10-10, до кода)

Для phone-only приоритет у валидного отдельного поля Контекст существующего manager block: 1–2 предложения ≤450 символов, без номера/ID/URL/технических меток. Контекст, подставленный парсером из Причины, не считается самостоятельной сводкой. Конфликт model phone с actual input либо новый вопрос вместе с телефоном переводит на текущий deterministic fallback. Prompt требует конкретный тур и вопрос, важные визовые/другие условия из истории; распознанное media описывает словами, без копирования ответов/программ.

Fallback выбирает тот же последний содержательный user turn, как N5; human media labels сохраняются. Вместо выдержки до1500 используется максимум одно короткое содержательное предложение paired delivered assistant до следующего user, пропуская приветствие/ack/footer. Вопрос ограничен200, предложение160, весь fallback450 символов. Если media unavailable, сообщить недоступность, не угадывать тур. URL удаляются до выбора предложения, чтобы ссылка перед описанием не подменяла тур. Предел450 и fallback применяются также к невалидным обычным консультациям. Сохранённая история и source номера не меняются. Без дополнительного AI.

N5 (историческая реализация, superseded N6; первоначально до кода): выделить deterministic contact-context helper из текущего phone override. Выбирать current non-contact question либо latest eligible user turn; только для выбранного historical turn собирать следующие delivered assistant записи до нового user. User media без подписи/вопроса также является источником: его placeholders humanize, не возвращаться к старому туру. Humanize exact internal media marker lines только для уведомления, БД сохраняет исходную provenance. Strip manager blocks и phone-bearing lines; bounded question1000/answer1500, Telegram context≤3000. Нет нового AI call/metadata schema; extra details подписаны «Клиенту ответили», чтобы каталог/ответ не выдавались за видимый текст истории. Отсутствующий/недоступный media контекст не реконструируется по старым ответам.

## S7: silent reaction → next text (до кода)

Parser возвращает kind=story_context с mid/sender/text=""/story.id, включая None для invalid/unsupported ID. Webhook после MID-дедупликации сохраняет валидный ID либо очищает старый, без collector. Cache dict insertion-order, monotonic TTL600с, cap10000; prune при записи, consume/check expiry при следующем содержательном событии. Только plain user без media/referral/phone-card получает приватный snapshot _reaction_story. Он не становится story до stateless merge: несколько plain texts окна остаются одним вопросом; смешанный media пакет получает собственный источник. Snapshot переживает новую реакцию во время ожидания, не читается из cache при dispatch. Manager/shutdown очищают; flags off не сохраняет hint. Invalid story/url не восстанавливаются по памяти/похожему изображению. Reuse прежнего exact story resolver/vision/fallback. Архитектурный choices CLI отсутствует; решение записано до кода без установки инструментов.
S7 merge boundary (до исправления): новый _reaction_story начинает отдельную plain группу; следующий plain без нового snapshot продолжает эту группу. Уже принятый q0 до реакции не поглощает следующий q1; reaction A→qA→reaction B→qB сохраняет оба exact источника и оба вопроса. Срез старого plain merger минимальный, новые sources не теряются.

## M2: reusable VIDEO for mentions/direct attachments (до кода)

Channel photo-like group extends to video; aligned input image_types сохраняется для любого non-image. prepare_images optional types направляет mention в _prepare_file(AUTO), direct video в _prepare_file(VIDEO), ordinary photo сохраняет прежний IMAGE путь. AUTO download принимает JPEG/PNG/MP4/octet/GIF, byte signature выбирает формат; VIDEO still validate_mp4 и existing timing/decoder. StoryMedia добавляет optional expanded image_types и media_types по исходным вложениям после caption, старые конструкторы совместимы. Frame labels включают source index; aggregate limits проверяются на всём наборе. Prompt использует output types, history — input index/resolved format. Empty all-GIF set молчит без вопроса, с вопросом вызывает только обычный text AI; partial failed media не отправляются AI. Explicit sticker/GIF events kind ignored резервируют MID до dispatch, не попадают в collector. File/product принудительно используют non-text manager handler, даже с вопросом.

## A2: resilient incoming boundary (до кода)

Проверять тип каждого контейнера entry/messaging/message/sender/recipient до .get и каждого MID/ID до hashing. Attachment type сохранять лишь как bounded ASCII identifier, прочие значения обозначать unknown; text всегда строка. Non-list attachments и explicit is_unsupported сохраняют non-text сигнал, не открывают media route. Неизвестное пустое message с MID — unknown fallback, deletion и настоящие service events без message не создают ответ. Невалидное JSON — 400 после signature check. Postback использует только visible title и собственный MID. Failure notification имеет отдельный клиентский текст; takeover повторно проверяется внутри lock и перед доставкой. Existing five-second collector, flags и content decoder остаются прежними.

2026-10-08. Объём: S1–S6 requirements.md; широкий медиа-проект отложен.

Канал переносит только валидированный ID истории (либо явное отсутствие ID) в событие с текстом. Такие события не склеиваются с вложениями соседних сообщений. Webhook сохраняет прежнюю MID-дедупликацию и запускает существующий фоновый обработчик с опциональным story metadata.

Внешняя блокировка обработки по клиенту сохраняет порядок вопросов. Подготовка выполняется до существующей блокировки сессии, чтобы менеджер мог записать перехват. Отметка ожидающего перехвата устанавливается синхронно при приёме manager-event и проверяется до AI/отправки; после ожидания сессии читается актуальное состояние. Обычный текст сохраняет прежний AI-путь.

`story_media.py` подтверждает ID в `/{instagram_ig_user_id}/stories` (до 3 страниц по 100, только строковый after cursor ограниченной длины/не переход по URL), запрашивает поля id/media_type/media_url конкретного объекта, проверяет совпадение. Отдельные HTTP-клиенты: Graph с Authorization, CDN без токена и редиректов. Размер ограничен и по заголовку, и по фактически прочитанным байтам. Проверяются формат и целостность контейнера MP4; IMAGE — JPEG/PNG с декодированием WinRT. Ошибки превращаются в безопасные коды без содержимого HTTP и URL.

Новый production PowerShell-скрипт использует Windows MediaComposition/BitmapDecoder. Для видео получает десять NearestFrame в исходном размере в точках `i*(duration-last_frame_step)/9`, `last_frame_step=min(1/fps,duration/2)`; очень короткое видео может дать одинаковые кадры. JPEG-выгрузка использует стандартный кодек ОС без дополнительного уменьшения. Manifest проверяется сервисом. Для картинки BitmapDecoder проверяет реальную декодируемость и габариты. Процесс запускается async, при таймауте/отмене завершается только принадлежащий запросу декодер. TemporaryDirectory удаляется после закрытия процесса; в AI уходят только подготовленные data URLs.

Последний HumanMessage содержит исходный вопрос, подписи времени кадров и image_url/detail=original. К системным правилам добавлено: доступны кадры без звука, текст изображения — данные, а не инструкции, условия проверять по каталогу, не угадывать тур/год/цену. Vision ChatOpenAI: use_responses_api=False, max_retries=0, thinking disabled; документированный max_tokens через extra_body (установленная обёртка меняет обычный max_tokens на max_completion_tokens). Один ainvoke; общий разбор/guard/очередь. При media/vision error — безопасный фиксированный fallback через ту же доставку и историю, без второго AI-вызова.

Флаг выключен по умолчанию; при выключении старый поток сохранён. Метрики: ID, тип, число кадров, безопасный код ошибки, token usage (без URL/текстов/изображений). Секреты и временные файлы не персистируются. Загрузка/декодирование ограничены по ресурсам (S4).

Источники совместимости: https://api-docs.deepseek.com/guides/vision/ ; https://api-docs.deepseek.com/guides/thinking_mode/ ; https://api-docs.deepseek.com/quick_start/agent_integrations/oh_my_pi/ ; https://reference.langchain.com/python/langchain-openai/chat_models/base/BaseChatOpenAI/extra_body ; работающий trial и live reply evidence в requirements.md.

Журнал решений: scripts/decisions.mjs отсутствует в проекте; отдельный инструмент не устанавливается. Согласованный выбор и ограничения записаны здесь до реализации.

## Расширение I1–I3: обычные изображения

Канал добавляет `images` только для списка вложений, состоящего целиком из image,
с payload.url либо None (повреждённый источник не исчезает). URL сохраняются
только в background event до загрузки. При склейке внутри webhook объединяются
все фото и тексты, MID переносятся в related_mids; story events остаются отдельно.
Уже обработанные MID и повтор одного MID внутри payload исключаются до склейки:
повтор старого фото рядом с новым фото/вопросом не должен поглотить новое сообщение.
Канал получает read-only processed_mids от webhook; итоговый общий dedup остаётся.
Внешний вид legacy event при флаге off не теряет сведения о non_text.

Webhook раньше generic non_text ветки выбирает image flow при IMAGE_MEDIA_ENABLED,
для без подписи передаёт служебную пометку вместо выдуманного вопроса. Общий
process_with_ai получает опциональный images список, вызывает prepare_images
вне session lock с существующей сериализацией. Истории имеют приоритет над image
attachments одного reply: точное story video нельзя подменить thumbnail.
Фото без подписи не устанавливает отметку 'получен текст' для соседнего post/Reel.

prepare_images переиспользует download/IMAGE decoder, проверяет каждый файл как
JPEG/PNG, в том же TemporaryDirectory удаляет исходник после подготовки. Метаданные
prepared media обобщаются: для own story есть story_id, для attachment отсутствует,
тип IMAGE. Ограничение 10 изображений и 24 MiB применяется до AI; source limit,
dimension/time/concurrency общие. Последний HumanMessage содержит все фото original
и точную подпись; system instruction различает story frames / ordinary images и
просьбу без подписи. Один вызов get_vision_llm, прежние guard/queue/manager checks.

Отказ изображения использует отдельное честное уточнение про фото (не 'историю').
Хранение истории не включает source URL; только реальные подписи, пометка
'Изображение без подписи' и число. IMAGE_MEDIA_ENABLED=false независим от stories.
Документация явно различает ответ на own story, пересланную историю, image,
ig_post/Reel и direct video; claims ограничены действительной маршрутизацией.

## Расширение P1–P5: публикации и Reels

## Micro N1/N2: phone-card и manager marker

Phone normalization до non-text classification после echo/reaction
guards; только phone_number/contact fields или generic Phone number-label и
полностью телефонный subtitle с непротиворечивым phone button. Ambiguous/mixed
карточки сохраняют старую ветку. По message.text совпадающий телефон не дублируется.
Phone text/card merge после MID-filter, related_mids сохраняет все MID. Cache
последних phone-only text inputs (30 с, <=1024) подавляет только повторную auto-card,
создавая MID-only ignored event для стандартного webhook dedup. Manager marker
regex допускает EOF; malformed header cleanup обрезает остаток служебного блока.
Empty visible reply получает нейтральный ack; notifier/limit/takeover остаются.
Safe template diagnostics фиксирует только schema keys/types/counts/phone booleans.
Notifier использует подтверждённый номер actual input при отсутствии/расхождении
model phone field. История прошлых assistant blocks очищается в prompt-copy,
без изменения SQLite. Cross-POST cache покрывает auto-card после plain phone,
обратный порядок отдельных POST не обещается. Unknown template в одном webhook
с phone-only text объединяется с текстом; без такого источника телефон не угадывается.
N1b: unwrap payload.generic dict в canonical generic view; empty nested generic
в отдельном POST преобразуется в MID-only duplicate лишь для single attachment,
без текста/story и с единственным recent phone-only input sender. Logger показывает
nested schema keys/counts, без содержимого. Notifier limit/takeover остаются.
N2b: при input_phone и отсутствии escalation_reason создать contact escalation
из actual input, bounded последнего содержательного user запроса и нейтральной
причины. После notifier выбрать deterministic phone-only ack; Telegram error
не превращается в ложное обещание. Единственный исходный AI-вызов сохраняется.
N2c: current contact context строится детерминированно при любом input_phone,
даже когда AI прислал marker. Current question имеет приоритет; prior user
contact с телефоном пропускается как источник запроса. Contact tag всегда
«контакт», AI old phone не попадает в контекст. Safe log хранит только boolean
model_phone_matches_input и sender, без номеров/контекста. No-input consultation
сохраняет существующий разбор model marker.

## Micro C2/C3: carousel child asset

Resolver различает explicit ID и candidate из CDN asset_id.
Для второго direct leaf IMAGE/VIDEO не возвращается до проверки own feed:
feed fields включают children{id,ig_id}; exact child match выбирает parent,
полный Graph parent снова проверяет child membership и тип CAROUSEL_ALBUM.
Совпадение permalink, если он задан, также обязательно. Не искать визуальные
аналоги и не расширять HTTP allowlist. Safe log хранит source kind/numeric
candidate/hash shortcode, без URL. В IMAGE native decoder [void] заменяет
pipeline discard массива pixels — пиксели по-прежнему прочитаны и проверены.

Micro correction R1 (до кода): собственный live webhook показал type=ig_reel,
который отсутствовал в _SHARED_POST_TYPES. Добавить его только для enabled shared
flow; при disabled флаге сохранить прежнюю non-text ветку. У источника сохраняются
только candidate ID/URL, обработка медиа остаётся в Graph resolver.
Safe diagnostic shared_media.context пишет тип, выбранный numeric ID, названия
известных identity fields и факт наличия URL; URL/подпись/сырой payload не пишутся.

Канал сохраняет только узкий shared metadata: media ID/URL и вопрос клиента; URL
существует лишь до resolver. Shared/text merge при флаге on сохраняет shared
sources и все тексты/MID; off оставляет прежнюю маршрутизацию. Отдельные share
и ig_post одного объекта выбирают источник с точным ID. Story reply приоритетен.

Resolver получает Graph id/media_type/media_url/caption/children для точного ID,
не запрашивает произвольные URL с авторизацией. Instagram permalink может быть
сопоставлен только с точным permalink в собственном /media; не угадывать ID по
shortcode и не парсить HTML. CAROUSEL children проверяются по порядку и полностью;
пагинация/слишком большой состав не должны давать неполный анализ.

Media decoder/download обобщается из существующего story пути и повторно
используется для VIDEO/IMAGE. Полученный caption — недоверенные данные публикации,
а не инструкции; system обозначает post/Reel/carousel и сохраняет каталог.
Общий процесс AI получает shared_sources вместо потери содержимого в blind marker;
один vision-вызов, сохранение вопроса и безопасной текстовой пометки публикации.
Подпись из Graph отмечена как данные и привязана к номеру публикации, как кадры;
при наличии ID и permalink resolver требует совместного совпадения обоих.
При inaccessible/unsupported/thumbnail-only — фиксированный честный fallback
без второго текстового AI. Флаг SHARED_MEDIA_ENABLED независим от story/image.

Реальная проверка собственного Reels обнаружила audio duration 8.658 с при video
duration 8.533 с: MediaComposition не может взять последний кадр по общей длине.
Перед декодированием считываем mdhd только у trak/hdlr=vide и передаём безопасную
числовую длительность через временный video-timing.json; временная шкала кадров
использует min(OriginalDuration, video duration). Звук не извлекается.
Повторная проверка prepare_shared_media: 10 кадров, 0.000–8.500 с, без AI;
full pytest 403 PASS, Ruff PASS. Подробности: runtime/windows-reel-last-frame.md.
## N4: fixed 5-second collector (2026-10-09, до кода)

Webhook проверяет signature и резервирует MID каждого raw event до помещения в sender buffer. Первая запись создаёт одну asyncio task с sleep(5), остальные дополняют список без сброса таймера. Flush забирает список до await, делает один stateless merge и последовательно вызывает прежние обработчики под processing lock. Manager event минует collector, синхронно ставит pending guard и отменяет только ожидающий buffer. Shutdown отменяет tracked tasks; cleanup не удаляет более новый buffer.

receive_message поддерживает unmerged вариант для collector; default сохраняет unit-level merge. Merge не хранит номер/время предыдущих запросов: пустой generic присоединяется только к содержательному событию текущего пакета с related_mids; подтверждённая карточка с тем же номером объединяется с фактическим текстом в этом пакете. Старые timestamp/cache эвристики удаляются. Сохраняются строгий parser карточки, question/story/referral guards, все raw MID, порядок текста и media identity. Неизвестные непустые вложения не считаются телефоном. Каждый story остаётся отдельным запросом со своим текстом; текущий phone source определяется последней явной phone-only/card строкой, не историей модели.

## M1: incoming story_mention → IMAGE pipeline (до кода)

Реализация: image_types передаётся от channel через dispatcher/_process_safely/
process_with_ai до build_full_prompt(media_image_types); длина и типы проверяются
до подготовки. Merge собирает image_types до изменения first.images, сохраняет
union non_text.types; обычные фото без mention не получают новый параметр.
System — contains mention, image labels — только соответствующие индексы;
history — [Story mention: изображения N], без URL/base64.

Канал распознаёт только attachment type story_mention и сохраняет payload.url через прежние bounds. Событие содержит images и метаданные источника с отметкой mention; merge изображений сохраняет соответствие тип ↔ порядок image, исключает посты и разные story reply. AI использует prepare_images и original vision; системное пояснение и history маркируют mention, исходный вопрос не подменяется. Не пытаться разрешать arbitrary ID или получать own story для истории клиента. Невалидный URL/контент отклоняется прежним media validator. Off и unsupported остаются прежними маршрутами.

## V1 cleanup: выбор владельца GigaAM (2026-10-10, до удаления)

**Результат:** GigaAM выбран владельцем; альтернативные runtime/models/helpers/caches removed, evidence exported locally. GigaAM retained smoke uses normalized float32 waveform (int16 is not accepted by onnx-asr),2intra/1inter/no-spin/offline. Wholeprotected6582SHA/health/PID and residualexclusivecache checks PASS; no production integration or mode selection yet. Mixed multi-engine benchmark helper removed from server; local historical helper/results retained for audit. См. runtime/gigaam-server-cleanup.md.

Владелец выбрал GigaAM и явно разрешил полное удаление других trial engines с сервера. Снять Whisper/Parakeet только из изолированных helper targets после inventory, private evidence export и pre/post seal. PowerShell LiteralPath и проверка разрешённых абсолютных границ/reparse points до всех recursive deletions. Не использовать общий pip purge/HF cleanup: shared caches включают действующую embedding-модель и production зависимости. Для pip HTTP cache удалять только пары metadata/body с ZIP METADATA Name, однозначно относящимся к faster-whisper/CTranslate2/Whisper/Parakeet runtime; прочие shared зависимости не трогать. GigaAM ONNX runtime сохраняется, production rollout ещё не выполняется; benchmark reports historical и сохраняются локально.

## Quick V2 design: incoming GigaAM voices (до кода, 2026-10-10)

Channel extracts `voice_parts` ordered text/audio slots plus `visual_parts` existing story/images/shared source descriptors only for supported voice events. `merge_events` contact cleanup first, then voice-aware supported contiguous per-sender groups containing audio; supported neighboring text/visuals become one `user_voice` with lossless MID/order/visual descriptors. Unsupported events are barriers, never discard them; voice-less groups use prior merger. Direct audio+image/story event preserves both. No signed URLs reach logs/history.

`voice_media.py` isolated client manages one lazy resident Python subprocess over private stdin/stdout JSON-lines (no HTTP port/auth endpoint). Python/model paths explicit settings, flag defaultfalse; runtime dependencies separate requirements-gigaam.txt, no production ONNX replacement. Queue admission cap8, acquisition30s; download+worker startup/STT90s. Bounded HTTPS allowlist and every redirect≤3 revalidated, no Graph credentials forwarded, actual byte limits/content encoding/length. Own temp files created only after global worker lock acquired. Worker SHA verifies existing pinned model and uses PyAV16.1.0 local allowed-format decoder; rejects video stream/remote playlists, header durations and actual sample count enforce aggregate180s. FLTP mono16k normalized float32, pause-biased~20s chunks with0.5s overlap (≤25s), conservative exact token suffix/prefix dedup. Shared stdout only protocol, stderr discarded (no media/text logs); protocol errors sanitized, no automatic same-request repeat. Timeout/cancel kills/waits owned process before temp cleanup, shutdown explicit close.

Main passes optional voice/visual parts into existing processing lock; existing typed/rate/takeover guards first. ASR outside session lock; async abort callback rechecks manager after queue wait, main after ASR and each visual. Prepare supported visuals sequentially via existing prepare_story/images/shared functions; aggregate≤100frames/24MiB, label original source. One existing prompt/AI/notification/history/send pipeline. STT failure produces deterministic manager escalation data (not model output), brief typed context and honest client acknowledgement based on notification success; no extra AI call. Full recognized text guard applies, current actual phone overrides stale model contact only when unambiguous explicit+digits. Preserve legacy call signature branches when no voice. Existing decisions-cli absent; owner choice/source links recorded here before implementation, no tool installation for ADR.

Sources: tested pinned onnx-asr0.12.0 API and existing native AAC/MP4 evidence; https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/utils.py ; https://pyav.org/docs/stable/api/audio.html (older stable-doc version, exact PyAV16.1.0 behavior requires native verification). WindowsServer2019 warning remains explicit; no new unsupported OS-support claim.

Implementation verification: exact PyAV16.1.0 native decode and isolated GigaAM worker/application-client proof PASS on original saved AAC/MP4 and M4A; six native cases including long input/silence, resident reuse/error restart/owned shutdown/temp cleanup. Exception path uses a dedicated deterministic no-LLM handoff helper to preserve brief context and honest send outcome. Runtime docs and manifests: runtime/gigaam-voice-integration.md.714 full tests/55 focused voice+5 early echo tests/Ruff PASS; explicit authorized production activation/deployed smoke/source/env/health PASS; live owner voice about Сербия recognized/answered14:16UTC without takeover. Before live retry, early own echo detection was fixed using scoped pending sends (recipient+actual sent text) and existing bounded MID cache; exact bugfix contract preceded implementation in bugfix.md, proof/runtime/limitations in runtime/instagram-early-echo-takeover.md.

## Quick N7 design (до кода)

Existing main pipeline сохраняет локальный outcome none/sent/failed/limit после попытки notify_manager. Finalizer удаляет из LLM видимой части предложения/части предложений с неподтверждёнными утверждениями о передаче/обратном звонке, сохраняет оставшийся полезный текст, вопросы и исходный URL/контактную строку. Финальное подтверждение по outcome добавляется перед контактной строкой; phone-only использует свои короткие проверенные acknowledgements с явным limit. No marker + false claim → none/limit outcome, не новая отправка. Prompt использует нейтральные формулировки по запросу/туру, запрещает предварительные обещания и оставляет решение об acknowledgement приложению. Голосовой/non-text limit fallback получает общий честный текст; failed fallback не утверждает отсутствие доставки при неопределённом сетевом исходе.

Telegram notifier проверяет HTTP200 и JSON ok is True. Transport/bad JSON/API failure → sanitized TelegramError. Существующий последовательный fanout продолжается после каждого TelegramError; успешная хотя бы одна доставка означает receipt, неполный fanout даёт warning только с количеством. Если подтверждений нет, raise; счётчик увеличивает caller один раз. Это изменение существующего helper, без новых зависимостей/эндпоинтов и архитектурного runtime. Decisions CLI ранее отсутствовал, новая инфраструктура не создаётся.

Regression matrix: phone-only/mixed question+phone/plain handoff/lying no marker/broken marker with count0/3 and notify success/error; useful text+URL/footer survive; history equals actually sent text/count accurate. Telegram ok true/false/malformed/network, partial-before/after/all-fail. Voice and unsupported limit outcomes; ordinary advice unchanged; prompt prefix cache retained. Server smoke mocks network/AI/send/DB and calls actual deployed source, production data/settings untouched.

## Quick N8 design (2026-10-11, до кода)

Channel emits user_silent_handoff for exact story_mention before visual/voice routing. Existing5s collector remains. Merge segments per sender around silent events and changed referral identities; use previous contact/voice/sender merger within each segment. Private referral survives replacement events; two distinct ADS retain their own question/media. Silent handler uses existing processing/session locks/takeover and count3, sends short human Telegram context, saves only incoming human provenance/count/time; no assistant entry/client send/queue on success/limit/error. Unsupported_type is not classified as invitation after explicit user rejection.

Sanitized referral carries bounded source/type/ad_id/ad_title and private validated-shape post_id/permalink/photo_url/video_url if supplied. AI functions receive optional referral; ad data becomes a separate HumanMessage text block, never client phone source. Exact identities route to existing shared media; provided photos/videos reuse existing preparation/decode under the same guards, labels distinguish supplied ad material from a full post. Mixed primary visuals+ad visuals reuse prepare_visual_parts shared10parts/100frames/24MiB cap. No Marketing API in production: current token proof failed; no guessed ad→post mapping. Persist only human ad title/provenance after processing, not media URLs/IDs.

Prompt security allows company business proposals as an explicit exception to unrelated-topic refusal; action policy gives a short thanks/one-question-if-needed and consultation marker, no invented decision on partnership or premature acknowledgement. Runtime N7 outcome remains final. No independent keyword classifier or phrase-deleting regex for «с радостью подскажу».

Tests: typed/raw story mention with image/video/audio and flags on/off; adjacent standalone text both orders; silent success/fail/limit/takeover/username race/dedup; no media/AI/send/queue. Ad nested malformed/title-only/exact source/unavailable/voice/photo/twoADS/sameADS/followup/standalone and URL-free logs/history. Prompt positive business/limit/prefix cache; existing unsupported/reel/file/product/story replies retain routing. Source architecture/dependencies unchanged, decisions CLI remains absent.

Verification:791PASS/8existingwarnings/Ruff/diff-check,3reviews clear; deployed3runtime files/backup/21SHA/env/launcher/health and mocked proof PASS. Mention precedes reaction; voice retains referral; media prompt preserves explicit business intent. Batch fixture mocks silent handler, conftest blocks real httpx network; BATCH_CLIENT incident disclosed. Coauthor classifier and exact full ad access remain open, unsupported routing unchanged. См. runtime/instagram-business-context.md.

Quick N9: root misunderstood circled prose as cooperation policy. Restore3 N7 literal constants and original tour media instruction; add general grammar/complete phrasing rule in BASE_RULES for every prompt variant. No text rewriting in main/guard and no new classifier. Only prompts runtime entry changes, other20manifest entries guarded. Proof compares old policy constants and checks full prompts plus prior known routes with HTTP/DB mocks. This supersedes N8 business exception without changing ads/mentions.

N10 discovery: inspect existing Meta token using allowed read-only identity/debug/permissions endpoints and safe allowlisted output. Bounded additional pagination checks only exact supplied shortcode, no analysis of neighboring media. Probe original asset only after proven identity; no credential family substitution guessed from prefix. Root checks access/archive; read-only ad_referral agent checks official documentation. No bot restart or runtime changes for research.

N10 authorized setup: use official Meta UI to inspect the existing app and obtain a separate Facebook User/SystemUser ads_read credential scoped to the correct advertising asset. Do not replace the PAGE messaging token. Probe exact ad and creative with allowlisted metadata, then fetch original video source privately and validate format/duration. Authentication may require owner login; no passwords/2FA guessed. UI/API grant and actual source proof are separate milestones. Full automatic ad routing remains contingent on proof.

N10 UI evidence before grant: confirmed owner's saved profile is logged in; existing Marketing API tools explicitly warn that generating a personal token revokes previous permissions. Avoid this action. Create a separate Employee system user named Sundita Ads Read Bot in the existing Sundita portfolio, assign only the target advertising account's ANALYZE/read task and the existing app prerequisites necessary for token generation; no administrative business role or campaign writes. If the UI requires broader rights, stop before granting them and document the actual requirement. Token limited to ads_read and bounded duration; existing conversion system user remains unchanged.

N10 least-role check: actual accepted system-user name is Sundita Reader. Exact ad proven in Ads Manager ID filter for Сандита Б2748504208879634. App ads_read already Standard/Active, no Advanced request needed. New token wizard exposes only two advanced scopes and hints missing app role. App task DEVELOP explicitly permits changing settings, so do not grant under read-only authorization. Try only TEST (UI: can test app), keeping ANALYZE on exact ad account and token scope solely ads_read. Official App Roles/Access Levels support tester testing permissions and Standard access for app-role users; SystemUser TEST→wizard availability remains an empirical question. If TEST is insufficient, document concrete blocker before broader grant. Sources: https://developers.facebook.com/docs/development/build-and-test/app-roles ; https://developers.facebook.com/docs/graph-api/overview/access-levels .

N10 exact-source diagnostic extension: issued ads_read token proves ad→creative and exact supplied permalink in Graph Explorer v26.0. Creative returns source/effective Instagram media IDs and FB video ID; FB video source GET is denied with code10. Before requesting more access, probe only those two exact IG media IDs using the existing PAGE credential at production Graph v25.0. Require returned ID and exact permalink equality before downloading any VIDEO media_url. Reuse bounded CDN downloader/MP4 validator/native10original-frame decoder; retain diagnostic files only in the existing artifact directory. Allowlisted report contains IDs, MIME/size/duration/hash/frame count, never credentials, signed URLs, raw captions or base64. No archive rescans, messaging calls, campaign mutations, production DB/settings or runtime changes.

N11 design: separate ad_media.py reads restricted credential file, uses Marketing v26.0 (actually proven) for exact ad/account/creative metadata, PAGE v25.0 for exact IG media. Resolve only well formed numeric IDs and valid IG permalink; effective candidate first, source fallback only matching same permalink. No published-media scan/video.source guess. Return resolved exact media body into shared decoder via a private kind=ad visual part; frame/caption labels identify advertisement. Reuse existing prepare_shared_media with internal resolver hook/typed private descriptor so fresh media URLs are downloaded once and not stored in DB/log/cache. Entire resolver bounded20s, no retries for permission/mismatch; no HTTP redirect or token forwarding to CDN. Credentials not Pydantic-readable token text, path only; read on call, failure reported by bounded reason code. Feature flag/account/token-file default empty/off. Main adds one ad part when ADS ad_id configured, preserving existing supplied ad visuals for featureoff/noadid; voice/customers grouped as before. Existing combined bounds/abort/onevision/history/escalation behavior reused. Startup read-only configured token permissions/account probe logs only scope/account match/expiry metadata, blocks enabling misleading configuration; no new public credential API. No SDK/dependency/runtime stack change; decisions-cli absent in this project, no fabricated ADR tool. Secure token transfer/rollout prepared only after green checks; issuance with changed lifetime requires explicit action-time authorization.

N12 design: add instagram_ads_account_ids string CSV, union with legacy single field; strip/deduplicate, all numeric IDs validated, maximum10 configured accounts and bounded input. _credentials returns token and ordered allowlist; ad.account_id membership required before creative access. Health loops exact configured act IDs inside existing20s deadline; any inaccessible/mismatched member fails explicitly. Meta Reader ANALYZE grants only approved К/С via official UI; same credential observes new assets without new scopes/duration. Exact ad probe then effective/source permalink matching and existing decoder, no account scans or guessed mapping. No new architecture/runtime/dependencies; existing decisions CLI remains absent.

N12 QA correction before rollout: pytest default project traversal encounters the newly private credentials directory; set testpaths to existing tests/ (all prior813 tests live there), preserving all fixtures/network/DB/native guards. No credential ACL weakening or test exclusions. Diagnostic exact ad.id filtered GET on all three approved accounts returns200/data empty; direct node remains100/33 after grants. Do not describe this incident as fixed without further source evidence.

N13 micro design: merge_events only flushes on incoming referral when the current segment already has a different explicit referral. Missing prior referral is not a boundary. Existing extraction/first-referral inheritance/mergers unchanged, no identity normalization or metadata enrichment scope expansion. Add meaningful order-symmetric photo+question+ADS tests checking text/media/referral/allMID, preserve existing twoADS and silent regressions. This prevents duplicate dispatch, but inaccessible ad may still invoke existing fallback once; do not claim media access fixed.

N13 source extension: inside existing ad media branch, for use_shared prefer prepare_shared_media(shared_sources) once with abort callback. Success uses its full incoming post images/caption and customer question, no Marketing read/extra ad label; media history remains true shared-source context. On StoryMediaError only, prepare_visual_parts(ad_parts) without repeating failed shared source; label successful fallback as exact ad as previously. Partial thumbnail/customer photos not accepted as replacement. Both failures follow existing _AD_UNAVAILABLE/manager route. Regressions assert no resolve_ad_media call on successful shared source, ad fallback on failed shared, oneAI, question present, takeover and total-failure behavior.

N13 review correction before rollout: fallback only for post_unavailable/graph_unavailable/media_timeout/download_unavailable. Identity/size/count/decoder guards rethrow and preserve existing manager failure path. Track shared_ad_fallback separately so history distinguishes unavailable incoming post from successful exact ad fallback. Voice+shared bundled inside visual_parts retains previous combined path; incoming standalone shared_sources preference is the narrow N13 scope. Review red4cases reproduced; corrected full840PASS.

N14 configuration design: existing N12 bounded allowlist supports4accounts; no runtime source change needed for approved original account. Official Meta Reader asset assignment ANALYZE only. Diagnostic directnode audit uses only log-observed numeric IDs and reports safe stage/type/http/code/subcode, no raw payload/media URLs. After API verifies4asset reads, use existing guarded rollout pattern: private env backup, exact single setting update, all other parsed settings equal,22runtime hashes/launcher unchanged, newPID/starttime around health, rollback env if verification fails. Real exact ad source→image/carousel/video preparation via existing guards, original quality and10video frames, noAI/sends. Dynamic variant ambiguity remains rejected. No unproven ad/source registry inferred from same5s arrival.

N15 micro design: retain kind=ad and exact legacy part when no supplied metadata; attach only existing allowlisted post_id/permalink/photo_url/video_url enabled by corresponding flags. story_media prepares ad part via full supplied post→provided clicked video/image→exact Marketing ID, abort before/after each attempt. Availability-only fallback reasons: post_unavailable/graph_unavailable/media_timeout/download_unavailable/ad_graph_unavailable/ad_timeout/ad_media_unavailable; identity/format/size limits remain terminal. StoryMedia adds optional ad_source provenance; combined preparation propagates it. Main labels and history distinguish clicked_asset from exact creative, including shared-source fallback. No resolver token/allowlist changes. Full incoming standalone shared_sources retains N13 priority. Safe log boolean presence fields provide future payload evidence without signed URLs/PII. Runtime scope main.py/story_media.py/channels/instagram.py; no new runtime architecture or dependencies.


## Micro N16 design (2026-10-12, до кода)

Current source proof: exact Elbrus Marketing node200/C sourceVIDEO already decoded10frames; three actual current referrals video_url=true fail invalid_media_url before Marketing. Official ADS JSON calls video_url a thumbnail. Change only main._ad_visual_parts / story_media._prepare_ad_part: fullpost→exactMarketing→provided photo IMAGE, availability-only alternatives, media guards unchanged. video_url retained privately in parser for safe presence/class diagnostics, excluded from fullvideo routing. Photo fallback provenance remains clicked_asset with completeness warning; fullvideo10original/noaudio unchanged.

Keep media failure code in process_with_ai. At prompt time, recognize an explicit catalog subject from actual === ТУР: ... === headings and normalized destination/name words (case/ё/punctuation tolerant; five-character prefixes for name words of at least five characters, exact whole-title three/four-letter names such as ВДП; exclude generic travel/program words). Only ADS-only media failure (availability or invalid optional URL), no independent story/images/shared/voice visuals, may use a text-only answer. Add unavailable-media statement in server-built ad context; clear media to avoid misleading partial vision. Do not clear failure for history diagnostics; suppress only automatic ad-failure escalation for this independent question. Normal model/contact handoff still applies. Unknown/vague ad-only asks and all other security/identity/format/completeness failures retain manager fallback. Tests cover original API success despite preview, fullpost identity guards, photo fallback, no thumbnail-as-video, catalog answers, vague unknown and failures, takeover/voice/othermedia/receipts/privacy.

No production client replay or paid AI. Verify corrected exact source preparation on server, mocked independent text/source pipeline, guarded source-only rollout with unchanged credentials/env/launcher/clientdata, baseline22SHA/newPID/local+publichealth. Scope is bug repair, not a new permission/architecture choice. Five unavailable ad IDs remain unresolved until direct source evidence.

## N17 read-only spike design (2026-10-12)

Separate identity discovery from decoding. Parent runs bounded existing-token official GET candidates against observed IDs only; read-only agents verify public SDK/reference semantics. Record HTTP/error/count/source identity metadata, never raw tokens/private payload/signed URLs. Manual original registration is excluded. No runtime source-cache architecture has been selected.

Live results: exact Ad and IGBoostMediaAd nodes denied for five failures; eleven supported effective statuses list589 company ads, no id/adset_id/source_ad_id matches. Including DELETED produces an explicit endpoint rejection and was removed, not ignored. Insights maximum without status filter returns positive controls in B/C but no five targets. Business Suite C exact331 filter with maximum dates returns no ads. Existing IG actor matches configured actor; connected-account reads provide no alternate company actor and business-scoped authorized_adaccounts remains100/33. Logs have no standalone events for five IDs. /MID/shares is200/data empty for all five. Preview control200/body iframe; failed331 preview100/33, no recovered source.

Browser candidate only: latest Business Suite View ad can provide the exact canonical source for a latest referral, as N16 proved on four associations. Before using it automatically, correlate the client and actual latest referral with the requested incoming MID/adID and recheck that no newer different referral arrived during lookup. Current UI has no per-message View ad, so older or ambiguous requests must stay unresolved. Exact correlation and unattended authenticated operation are not proved; the existing Facebook session has not been persisted to the server. Do not substitute the latest source into an older request. Instagram company-login browser investigation cannot proceed because the owner has no login. Full source decoding remains the existing strict IG/permalink/original pipeline, not preview decoding. Runtime implementation remains open pending a proved automatic identity path; no browser worker or credential storage was added.

Read-only identity review correction: before/after latest MID/adID equality only limits some races; it does not prove that the global Viewad header has updated to this referral. Username/text/date confirm the dialog, not the advertisement identity. Required missing signal is a visible exact Ad ID or a source link unequivocally attached to the exact incoming message. Do not populate an automatic adID cache from the proposed latest-dialog guard alone. N16's four case correlations and strict original-media retrievals do not establish an unattended general binding algorithm. No Page/IG get_ads reverse enumeration is present in current official SDK; media/promotable posts alone cannot restore this missing identity.

## Micro N18 design (2026-10-12, до кода)

Gate ADS in the existing serialized processing body before advertising media/AI. Reuse catalog-title matching for current customer text and bounded deterministic recognition of an independent catalog/visa-support request. Only use a recent server-recorded same-ad known customer subject for dialog follow-ups; never derive identity from referral title or raw history ad markers. Store only the exact numeric ad ID, customer-context validity/time in private session JSON (not history/prompt/log URLs); no schema migration. An ordinary unrelated processed customer turn invalidates the ad context. Voice input uses existing GigaAM then the same gate before visual preparation; unclear ADS voice failures remain silent.

Extract the existing silent helper's notification body into a same-file internal helper that takes only the session lock; the public service-event helper retains its processing lock. The normal pipeline already holds that processing lock, so invoking the internal helper prevents recursive-lock deadlock. Add an ADS reason with bounded human summary/current phone and no response/queue on any outcome. Parser preserves standalone ADS as user_silent_handoff/ADS event with optional bounded receipt identity, so existing silent boundaries protect adjacent messages. Normal known-context ADS keeps the current pipeline and honest N16 text fallback on media availability failure; media/security/takeover guards remain.

N18 review corrections before rollout: ADS dispatch must precede every generic non-text/file/product branch. Existing human-only file/product requests also stay silent when attached to ADS; unrelated non-ad files/products retain their previous route. _process_safely handles an unexpected ADS exception through silent handoff rather than the generic technical reply. Missing standalone MID uses a stable hash of sender/timestamp/adID when the webhook supplies a valid integer timestamp, permitting normal receipt dedup without persisting raw source URLs. Known independent visa-support/catalog requests use the same honest text-only fallback when the ADS media alone is unavailable. Source review and meaningful raw parser→dispatch regressions verified these corrections.

## Quick N19 design (2026-10-14, до кода)

Use the existing single ainvoke with an ADS-specific prompt response contract: JSON object {decision: answer|handoff, reply: string, context: string}. Program validates the envelope without another model/classifier call. The prompt's final ADS contract overrides greeting/footer/clarification for handoff: reply is empty even when the notification limit is reached. Answer reply retains ordinary response and existing optional manager marker. Context is a short human gist, never a full response, ID, URL or phone. Actual contact is extracted by the program. Missing/invalid envelope defaults to silent handoff; schema/transport failures are not customer replies.

Remove lexical clarity and recent-ad state gates. Advertising media preparation can retain existing exact-source guards, but its failure cannot substitute an unavailable template for the model call. Failed voice/visual preparation supplies safe typed text plus explicit unavailable status. Unsupported ADS file/product metadata is carried as a bounded human-only flag; model is called first, then unsupported attachment safety keeps human routing. Standalone ADS uses the ordinary serialized processing path despite its parser's silent-event type; Story mention retains its original silent no-model route. No processing-lock recursion. Normal notification/history logic handles the model's silent handoff; skip all visible receipt/phone-ack/send/queue branches for it while recording only actual user text/context. Keep source and service payload out of conversational history.

## N20 investigation boundary

No new architecture selected or implemented. Existing exact Marketing creative
to Instagram original path is live-proved for the screenshot source. Activities
does not recover the tested inaccessible ID within the checked window/accounts.
Official comments webhook explicit ad_id/original_media_id pairs are a possible
automatic index input, contingent on receiving a comment event and appropriate
existing permissions/subscriptions. This is partial coverage, not a universal
fallback or justification to bind latest global inbox headers to historical DMs.
Full evidence and limitations: runtime/instagram-business-context.md N20.

## N21 research correction

Official IGMedia boost_ads_list provides ACTIVE boosted ad IDs for an organic
media item; N17's absence of an IGUser get_ads method does not exclude this edge.
Existing token probes produced no mapping, so no index/resolver change selected.
For BM-assigned Page roles, official IG requirements combine instagram_basic,
pages_read_engagement and ads_read (ads_management is an alternative, not required).
Current separate tokens do not form one permission set. This is an untested
combined-token hypothesis, not established cause of direct Ad100/33. Any next
diagnostic must preserve bot credentials and limit grants to authorized company
read access. Evidence: runtime/instagram-business-context.md N21.

N22 experiment outcome: combined USER identity produced a positive boost mapping
for the working organic control, but not four problematic media, and direct failed
Ad remains100/33. No runtime design selected. Explorer permission selection affects
shared user grants, not just a temporary token: original Page scopes were restored
after an unintended narrowing and verified with live read-only health/subscription
checks. Future diagnostic token flows must preserve the full existing consent.

## Micro N24 design (before implementation)

Keep the existing single model decision/reply contract. Add opt-in JSON format to
the visual factory for ADS only, contingent on primary provider documentation.
Parser normalization removes whitespace and one complete outer ```json fence
only; never search for an arbitrary JSON substring or infer answer from prose.
Retain all schema and size checks. Factor validation reason into a pure helper
while preserving the existing dict-or-None parser interface where practical.
Reject an explicit output-length finish before accepting an envelope. Emit only
fixed rejection reason, safe length/type/token counts and allowlisted finish
reason; never raw model text, provider exception, prompt or image URLs.

Technical handoff uses an internal cause code and existing human context
sanitization to include the current customer question (not historical content or
model prose). Preserve one call, no automatic JSON-repair request, and all
customer-silence/count/phone/takeover controls. Meaningful parser/visual routing/
factory/fallback/log-redaction regressions precede implementation; full suite,
Ruff, diff check and read-only review complete local verification.

N24 verification: implemented as scoped keyword-only json_mode on existing visual
factory; defaults preserve ordinary vision. Validation returns fixed reason codes
with the old parse wrapper preserved. Provider failures are caught inside the ADS
call path without logging provider exception content; safe response metadata also
feeds visual completion counts. Independent review/60targeted/979fulltests/Ruff/
diff checkPASS. No server rollout or live model call; N23 original malformed
responses remain unavailable, so tests prove the repaired contract and routing,
not retrospective recovery of those responses or universal model compliance.

N24 authorized deployment: staged llm/main proof and factory JSON body checks
passed before guarded two-file replacement. Backup/manifest/env/launcher/ads
credential preservation verified; changed listener identity and local/public
health verified after restart. Installed same18mock casesPASS; no client replay
or real model call. Safe report:n24-applied.json and runtime N24 rollout evidence.

## Micro N25 design (before implementation)

Keep the ADS JSON decision/reply/context contract and strict validator. Add one
bounded retry inside the existing model invocation path only for string content
whose strip() is empty, with no reported length truncation. Reuse the same model
and messages, without rebuilding/downloading media or recording intermediate
history. Check manager pending/persisted activity before a repeat and after each
model await. Use final response metadata for validation and technical fallback;
provider failure on the second attempt remains a provider_error. Cancellation
is not an ordinary provider exception. Log the first empty response as a retry
event with safe metadata, then let existing final validation log failure only
when recovery fails. Existing notification/phone/limit/receipt logic stays shared.

N25 verification: one bounded loop in the existing invocation path, plus fresh
session guard after try/except to preserve manager pause even when the second
provider call fails and notification is limited. Read-only review clear after
its edge-case reproduction/fix. 90 targeted/1009 full tests/Ruff/diff/micro-spec
checkPASS. Provider responses are mocked; no runtime deployment/live trial.

## Micro N27 design (before implementation)

Reuse the N25 loop and its two-call global bound. An explicit allowlist of
repairable JSON/schema rejections controls the second call; finish_reason=length,
response_too_long, invalid_type and provider failures stay terminal. No lenient
normalization of unknown fields. For schema/JSON errors, extend a copy of the first
system message with the complete three-field contract and safe rejection code
in a new list; retain all other messages and the final user position. Do not include raw rejected content. Keep
the empty-response retry's original unchanged messages for compatibility.
Retain takeover checks around awaits and the existing safe final fallback. Keep
the empty retry event; add a format retry event with metadata only. The private
journal retains both attempts under a shared request ID. Tests inject malformed
first responses deterministically and exercise takeover, cancellation, final
failure, ordinary traffic and image identity; real API probes verify corrected
regeneration but cannot recover the body of the historical invalid_fields event.

N27 verified:29new/146focused/1071fulltestsPASS, 8existingwarnings/31.07s;
Ruff/diff/micro-spec and independent reviews clear. Three real corrective API
calls valid after synthetic first defects. Rollback/24baselineSHA/backupPASS.
Automatic approval review blocked production apply before execution; approval pending.

## Micro N26 design (before implementation)

One synchronous best-effort journal helper at the sole ainvoke completion site,
before parsing/takeover. Create UUID once per processing and reuse it across N25
attempts; pass content plus bounded explicit metadata, never messages/response
object/exception text. Use a dedicated non-propagating stdlib logger and UTF-8
RotatingFileHandler,5MiB+7archives, with an overridden handleError that cannot
print a failed raw record. Creation/write/redaction failures log safe fixed codes
without changing the application outcome. Lazy handler is reused and closed when
path changes; tests redirect it to tmp_path and close it on teardown. Files are
created mode0600 where supported; Windows inherits server log-directory ACLs.
Mask configured secrets and recognizable token/media forms before truncation;
non-string content is represented only by its type. Default enabled config toggle
allows a later explicit disable. Ordinary bot log receives only trace metadata;
ADS rejection events include the same UUID to locate the private journal entry.

N26 verification:27new/117targeted/1036fullpytestPASS,8existingwarnings/38.72s;
Ruff/diff/micro-spec checksPASS. Independent privacy review found short configured
secrets and additional credential syntax; sixRED regressions preceded fixes and
re-review is clear. No production changes or extra model inference performed.

N25+N26 authorized rollout: three sources installed with23-file manifest, verified
backup/atomic replace/guarded rollback and preserved private settings. NewPID17148
and local/publichealth confirmed independently after SSH exit1 during restart.
Staged and installed29mocked scenarios/dedupPASS, with journals redirected to
bundle synthetic files; no live model trial or production journal test payload.
Production journal is created lazily at the first received real response.
## Quick N28 design: один контракт ответа (до реализации)

Global response schema: {reply:string,manager:null|{context:string,type:string,
name:string}}. Null means no notification. Empty reply with manager means silent
ADS; nonempty reply with manager means reply plus human handoff. Remove redundant
decision/reason and model-generated phone. Input phone still forces contact flow.
Replace current ADS validator/retry with route-independent validation at the sole
ainvoke seam in main.py; keep existing metadata/redaction journal and route tags.
Text get_llm and vision get_vision_llm always JSON; remove separate get_llm_json
and json_mode option. Keep provider models/settings except text temperature0.1
matching the existing structured text route, timeout/token budgets unchanged.

Prompt: one global format block after dynamic rules, with three valid examples.
ADS block only selects silent vs meaningful answer, referencing same manager
object. Rewrite every marker-producing business rule, review/contacts/limit/
closing instructions. Limit is enforced by code; model may express manager need
even at cap, while program truthfully reports no new notification. A response
containing manager/booking service markers is rejected, never parsed for actions.
Keep marker stripping only for legacy history and defensive context cleaning.

All attempts are journalled before fresh takeover checks, same request ID. A
trusted format-only reminder gets one retry; raw faulty output is never inserted.
Malformed final JSON or provider error becomes fixed technical manager context;
ordinary routes get a fixed honest customer reply with actual notification receipt,
ADS stay silent. Program-generated media/STT/guard messages are outside JSON.
No media/download/STT repeat. No changes to event routes, DB, sessions, batch5s,
server configs or deployment manifest. ADR via decisions.mjs before implementation.

Verification: strict schema/duplicates/nested values, all three outcomes, plain
text/ADS/vision/voice/mixed routes, two-call bound, takeover/cancel, terminal errors,
phone authority/current question/context/history, actual delivery/count/cap and
private logging. Update old marker fixtures explicitly; keep malformed responses
raw in negative tests. Full offline suite includes native decoder requirements.

N28 verification completed:68new/1136fullPASS,3real full-handler text casesPASS;
see runtime/unified-model-json.md and ADR0005. Existing N27 recovery is incorporated
into the common two-attempt loop. Old N27-only two-file rollout is superseded by
the N28 four-file candidate (main/prompts/llm/llm_response_log); no rollout executed.

N28 deployed on explicit owner «деплой»: existing guarded four-file atomic rollout,
verified backups/rollback, unchanged protected configs/client data, synchronized
installed manifest24entries. NewPID15716, local+externalpublichealth ready;
installed common contract and text/vision JSON payload verified without requests.

# Quick N29: изолированный tool calling spike — 2026-10-18

## Quick N32 — all clients (до кода)

Решение: .kiro/decisions/0011-global-tool-transport.md (accepted).

Literal scope allowlist/all по умолчанию allowlist; gate сначала проверяет
непустой str ID, затем scopeall или точное членство. Один frozen use_tools на
запрос уже обеспечен N31. Healthall без фиктивного количества клиентов.
Расширить существующий guarded rollout controller target_scope параметром;
для all добавить только новый envkey, оставить числовой allowlist и recovery
настройки прежними. Backup/atomic/rollback общие, verify учитывает target scope.

Факт: scopeall deployed,1379testsPASS; priorcanary rollback и новыеDBreceipts
проверены.3source changes в5filepackage,28SHA/env/protected/PID/healthPASS.
Installed proof подтверждает all gate/text+vision schemas,0networkcalls;
postrestart новые model records0 на момент проверки,не гарантия качества всехответов.

## Quick N31 — canary rollout (до кода)

Решение: .kiro/decisions/0010-tool-transport-canary.md (accepted).

Независимый numeric allowlist в settings; per-client выбор до сборки prompt,
factory и parse, один bool на всю попытку/retry, без глобального mutable scope.
Legacy prompt/result path воспроизводится по installed baseline; N30 strict tool
сохраняется для allowlisted ID. Config default off. Никаких изменений recovery
allowlist, model names, credentials, БД или сообщений. Runtime payload включает
только изменённые source files; backups/config exact copy и inverse rollback
без восстановления устаревшей БД. Installed manifest обновить после proof.

Факт N31: deployed5files+DEEPSEEK_TOOL_CLIENT_IDS, installed28manifest synced.
12legacy prompts/retries и обеfactory payload совпали с backup на сервере при
запрещённой сети; машинные/пользовательские/launcher overrides отсутствуют.
Health даёт только enabled/allowlist/client_count, без клиентских ID.
Live tester1toolcall valid→answered/done→2parts sent с receipt/attempt1 каждая.

Extension10: использовать существующий tool_call_probe и штатный build_full_prompt,
strict beta + thinking.disabled во всех десяти случаях. Vision serializer прежний,
detail original; фото и десять кадров имеют проверенные SHA и собственное
происхождение. Предварительная сборка запрещает сеть; run разрешает только
DeepSeek API. Смысловые ожидания фиксируются до run, исходные arguments и безопасные
метрики сохраняются отдельно. Ошибки не замещаются успешными повторами.

Основной runtime не меняется. Endpoint обычного tool — текущий chat/completions;
для strict — официальный /beta/chat/completions. Удаляется только response_format,
описание prepare_response содержит существующий reply/nullable-manager schema;
форматный блок заменяется инструкцией вернуть один вызов этой функции, без
побочных действий. Named tool_choice и thinking.disabled задаются явно.
Сырой function.arguments проверяется существующим _validate_response, включая
duplicate keys, service markers и silent-context. Никакие вызовы функции реально
не исполняются; tool result не является Instagram/Telegram receipt.
Проверка до шести HTTP: старый JSON control, обычный tool дважды, strict tool,
manager reply, silent. Последние два используют strict только если strict-проба
успешна; иначе обычный transport. Автоматических retries нет. До оплачиваемого
run — offline parser negatives, read-only review и preflight с внешним HTTP deny.
Начатые запросы отмечаются до сети; существующий report блокирует повтор run.
Текущие исходники, настройки, сессии и обычная обработка сохраняются.

N29 evidence: user approved six new calls; six completed. Original JSON still
failed; ordinary forced tool twice and strict problem/manager/silent all returned
one prepare_response with validated original reply/manager arguments. Strict
nullable anyOf accepted by actual beta endpoint. Server28SHA/env/health preserved.
This establishes text transport feasibility only. No runtime migration or full
handler/vision verification implied; existing ADR0005 business contract remains.

Extension10 evidence:10 strict beta calls all valid; photo1+video10 keep original
detail. Actual model deepseek-flash; latency1.64–3.28s, mean2.37s. Semantic manual
review9/10; limit warning omitted, requiring existing deterministic finalizer
rather than trusting model prose. Incorrect VDP predicate corrected separately
without changing original paid responses/report. Contact intent only; newest
phone extraction, actual Telegram cap and receipts are outside direct API scope.

## Quick N30 design — 2026-10-18, до кода

Решение: .kiro/decisions/0009-model-tool-transport.md (accepted); бизнес-контракт
по-прежнему .kiro/decisions/0005-unified-model-json.md.

Один schema/extractor в src/services/llm.py: factory text/vision возвращает
малый subclass ChatOpenAI с одинаковым forced strict tool и beta base URL.
Установленный SDK теряет raw arguments: subclass до super снимает tool_calls
с копии provider message, а исходное message сохраняет в additional_kwargs
raw_tool_message после super. Общий extractor читает только raw_tool_message,
не AIMessage.tool_calls parsed dict, затем handler вызывает прежний
_validate_response. Metadata length приоритетнее остальных ошибок. Ошибки
конверта добавляются к ограниченным format retries; plain JSON не fallback.
Тесты старых JSON fixtures перевести на настоящий AIMessage tool envelope,
сохранив негативные аргументы и все прежние бизнес-проверки.

Prompt говорит только об аргументах prepare_response; reply/manager бизнес-схема
прежняя. История остаётся видимым текстом — tool response заканчивает наш
application cycle, tool messages/result в будущую историю не добавляются.
Лог диагностирует исходный envelope/arguments, существующие redaction/caps
сохраняются. Recovery и delivery модельный transport не знают; checkpoint
остаётся прежним сериализуемым plan. ADR фиксирует замену транспорта, не данных.
