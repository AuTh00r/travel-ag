# Tasks: ответы на собственные истории (Quick Spec)

## Quick N42

- [x] N42-a: воспроизвести не-JSON ответ настоящим SDK без внешней сети;
  проверить документированную семантику сетевого timeout.
  Факт: установленный OpenAI2.44.0 возвращает str для HTTP200 text;
  реальный MockTransport503→str→ChatCompletion даёт3вызова/1IGreceipt/0TG.
- [x] N42-b: typed boundary, общий deadline, безопасные тип/elapsed в логах,
  понятная техническая карточка; сохранить бюджет/отмену/outbox.
  Факт: ProviderResponseError, wait_for120/120/240, elapsed_ms/response_type;
  HTTP body закрыт до retry. Ошибки обработчика не утверждают отсутствие
  частичной отправки. ADR0020 через scan/add/review5/6/approve accepted;
  см. .kiro/decisions/0020-provider-response-deadline.md.
- [x] N42-c: профильные и полный pytest, Ruff/diff, read-only review;
  обновить evidence. Без деплоя, платных вызовов и production-изменений.
  Факт: исходные8RED→39PASS; расширенные141PASS, затем20PASS с дополнительными
  регрессиями/устойчивым SDK deadline. Полный1809PASS/8прежних warnings/100.37с,
  Ruff/diff PASS. Независимое review: найден и исправлен неточный текст о
  доставке после ошибки обработчика. Сервер только readonly: jobfailed_final,
  model_attempts2, Telegramsent4, manager_last_atnull. Перезапусков/отправок0.

| Progress N42 | Status |
| --- | --- |
| N42-a–c | Готово локально,1809PASS; не выложено |

## Quick N41

- [x] N41-d: authorized deployment of three runtime files, backup/restart/postflight.
  Факт:31Oct20:32Минск, PID19360 ->428/start17:32:32.3044109Z.
  Source/SQLite backup проверен;3файла и35manifest entries совпадают.
  Local/public healthok, schema/integrity PASS, свежих ошибок/warnings0.
  Все1707прежних sessionstates и1108receipts сохранены, env/credentials/
  baselines/allowlist/catalog8 прежние. Ручных paidcalls/отправок0.
  Пакет4d199cfc44786489b61b195f9c550cf44e5ba22fcc35049e349973052b86f5e2.

- [x] N41-a: route exact unsupported_type to the silent manager handoff.
  Факт: приоритет exact unsupported_type, нейтральная карточка Non-text и история;
  используется существующий silent barrier и лимит уведомлений.
- [x] N41-b: test isolation, context, batching and no client response; run QA.
  Факт: профильные119PASS до изменения приоритета ADS; повтор63PASS после него,
  включая ADS. Ruff/diff PASS. Только локально, сервер не менялся.

| Progress N41 | Status |
| --- | --- |
| N41-a–d | Deployed31Oct20:32Minsk; health/schema/35SHA PASS |

- [x] N41-c: повторная независимая проверка и устранение найденных пропусков.
  Факт: RED для exact API unsupported_type -> user; исправлено сохранение типа
  в нормализации, включая приоритет над противоречивым GIF MIME. Ошибка username
  допускает уведомление по числовому ID; StaleWork пробрасывается. Добавлены
  проверки соседних сообщений, лимита/ошибки/паузы/отмены, API/webhook parity
  и recovery-доставки. Профиль105PASS, read-only review без новых замечаний;
  полный итоговый прогон1694PASS/8прежних warnings/98.80s, Ruff/diff PASS.
  Сервер не менялся. Артефакты: n41-recheck-20261031.

## Quick N40: технические ошибки без сообщений клиенту

- [x] N40-a: подтвердить текущие причины, оформить контракт и ADR через CLI.
  Факт: спек до кода; ADR0019 через scan/add/review5/6/approve accepted.
  См. .kiro/decisions/0019-silent-technical-handoff.md.
- [x] N40-b: добавить регрессии трёх попыток, таймаутов, terminal-ошибок,
  молчаливого финала, безопасной диагностики и менеджерского перехвата.
  Факт:4исходных RED; после реализации SDK41PASS, профиль486PASS;
  расширенные проверки persistence/trace/core130PASS. Полный результат см.N40-d.
- [x] N40-c: внедрить ограниченный вызов, точные логи и молчаливую надёжную
  доставку технического уведомления; исключить перемножение recovery-повторов.
  Факт: primary120/120/240, SDKretry0, durable budget+log; failed_final без
  Instagram. Technical tasks вне бизнес-лимита, отдельные source key/part;
  unknown не повторяется, перехват отменяет задачу. Read-only review PASS.
- [x] N40-d: профильные и полныйpytest, Ruff/diff, независимое read-only ревью;
  обновить факт/ограничения. Никаких платных вызовов или деплоя.
  Факт:1674PASS/8прежних warnings/98.84s с отдельным basetemp и разрешённым
  нативным декодером. Ruff/diff PASS. Финальное read-only ревью без блокеров;
  исправлен найденный остаточный non-text fallback. Runtime note добавлена.
  Сервер/клиентские базы/флаги/секреты не менялись, платных вызовов0.
  Названия прежних регрессий обновлены под новый контракт; повтор276PASS.

| Progress N40 | Status |
| --- | --- |
| N40-a–d | Готово локально;1674PASS, Ruff/diff PASS; ADR0019 accepted |
| Production | N40 выложен31Oct12:58Минск; health/schema/35SHA PASS |

- [x] N40-e: разрешённый владельцем31Oct деплой10файлов, source/SQLite backup,
  контроль миграций и health, сохранения настроек/данных/receipts и отсутствие
  свежих ошибок. Не расширять recovery и не выполнять ручных платных вызовов.
  Факт: изолированный rollout/inverse proof PASS, включая частичную замену,
  отказ онлайн-отката после запуска и сохранение receipts/unknown/history.
  Пакет6b1de0a1c59b1521f6ff45ff6a43b9a09b939bba353676730d91f1b88d604afb.
  Backup проверен,10файлов иmanifest35entries установлены, PID19360;
  local/public HTTPS healthok, schema/integrity PASS. Все1706прежних states
  и1104receipts сохранены; env/credentials/8туров/allowlist/baselines прежние.
  Новых logerrors/warnings/tracebacks0. Ручных платных вызовов/отправок0.

KNOWN-RED:N40-ADR-BASELINE (2026-10-31; owner: meta-diagnostics/tour-sync specs):
общий decisions.mjs check exit1 на трёх ранее существовавших замечаниях связности
в meta-diagnostics/requirements и tour-sync/{requirements,design}; те же три
файла были перечислены scan до N40. ADR0019 отдельно reviewed5/6 и accepted.
Нерелевантные спеки и их архитектурные решения в рамках N40 не меняются.


## Quick N38: полная диагностическая цепочка

- [x] N38-a: record scope/diagnostic architecture and audit current sinks/call sites.
  Факт: Quick scope recorded before implementation; CLI ADR review6/6, accepted.
  См. .kiro/decisions/0018-private-processing-trace.md.
- [x] N38-b: implement private bounded trace, immutable explicit request capture,
  secret/media redaction, safe correlation and response mirroring.
  Факт: separate JSONL trace20MiB+7backups,512KiB encoded-byte record bound;
  explicit serializer, immutable messages, request/parent/job/task/delivery IDs.
  Shared media aliases cover objects and encoded JSON; no arbitrary repr/dumps.
- [x] N38-c: instrument inbound/model/review/finalization/notification/delivery
  outcomes, separating provider and durable confirmation without business changes.
  Факт: primary/review/retry capture, normalized inbound/skip/final text/pending;
  IG/TG provider confirmation and committed SQLite receipt are separate events.
  Legacy missing MID records durable unknown. No new model calls or queue rules.
- [x] N38-d: regressions for redaction/limits/fault isolation/correlation and full
  offline pipeline; full pytest/Ruff/diff plus independent read-only review.
  Факт:1639PASS/8preexisting warnings/81.72s, Ruff/diff PASS. Independent read-only
  audits found encoded-secret/media/nested-URL bypasses and a missing durable
  trace branch; fixed with regressions. Initial full-run mock-instance leakage
  was isolated to the new test and corrected by class-level patching; full rerun
  green. Model/transport side effects stubbed; no weakened delivery assertions.
- [x] N38-e: document contents, limits and operational use; report local status,
  no paid calls or deployment.
  Факт: n38-diagnostics.md, combined14runtime-file release notes and runtime note
  prepared. N38paidcalls0, productionwrites0, deployment0; source manifest saved
  separately from historical N37 live-evaluation manifests.

| Progress N38 | Status |
| --- | --- |
| N38-a–e | Implemented and verified locally;1639PASS, Ruff/diff PASS |
| Production | Combined N37/N38 deployed29Oct; health/schema/34SHA PASS; scope unchanged |

- [x] N38-f: package authorized combined14file rollout; verify installed baseline,
  guarded source/online SQLite backup and exact rollback including partial apply.
  Refuse old-code rollback with active N37 task/outbox; never restore old DB.
  Факт: package6cc07643, local/server isolated inverse proof PASS (full/partial,
  bad backup, postrestart rollback refusal, receipt/unknown/history retention).
  Onlinebackup integrity PASS. Independent review closed rollback TOCTOU by
  forbidding old-code rollback after restart; early inverse requires original
  PID/start. Restart guard includes Python descendants of listener only, keeps
  ancestor/controller siblings denied; family regression proof PASS.
- [x] N38-g: install/restart normally; verify hashes/health/schema/catalog/logs,
  unchanged env/credentials/recovery scope/baselines and retained receipts.
  Факт:14files installed,34runtime SHA matched;3836 ->11164/start19:20:39Z.
  Local/publichealthok; schema/integrity/catalog8/SHA82aa7b12 PASS;974previous
  receipts/1659previous client sessions retained. Env/credentials/allowlist1/
  baseline unchanged. Trace writer/deployment marker+21inbound records verified;
  fresh startup/logger error markers0. First transient readiness verify was
  red, repeat same verifier green; no repeat install/restart/rollback performed.
- [x] N38-h: save deployment evidence and operational limitations; no synthetic
  paid API or Instagram/Telegram sends inferred from the deployment instruction.
  Факт: safe server postflight/diagnostic/proof/installed manifest captured;
  canonical manifest synced only14authorized entries. Old-code online rollback
  disabled; backup retained. No manual model calls/sends; fresh natural complete
  model/review/delivery chain remains unobserved after this rollout.

## Quick N37: проверка и обновление эскалаций

- [x] N37-a: record approved scope, architecture decision and regression matrix.
  Факт: approved Quick scope recorded before code;21 anonymized intents;
  см. .kiro/decisions/0017-reviewed-manager-tasks.md (review6/6, accepted).
- [x] N37-b: align clarification rules; implement bounded candidate review and
  exact-input catalog diagnostics, preserving mandatory routes and takeover.
  Факт: one forced review_handoff,25s timeout/max_retries0; malformed/length/
  provider/timeout retain valid primary. Exact catalog hash/names/dates in both
  phases; source-incomplete constraint and takeover rechecked. SDK payload tested.
- [x] N37-c: persist open tasks and confirmed per-chat versions; implement send/edit
  intents for legacy and recovery, counting new tasks once and preserving unknown.
  Факт: manager_tasks+changes,per-chat outbox/CAS; send/edit confirmed IDs only;
  legacy worker restores safe retries, never unknown. Confirmed first task counts
  once, updates allowed at3; takeover closes permanently. Old schema migration,
  partial4chat/restart/unknown/concurrent-version/takeover/legacy count covered.
- [x] N37-d: verify 21 anonymized cases and failures/partial/restart/takeover paths
  offline; full pytest, Ruff, diff and independent read-only review.
  Факт:1594PASS/8preexisting warnings/72.06s; final full run with native Windows
  decoding outside restricted sandbox, no policy changes. Ruff/diff PASS.
  Read-only review found missing legacy retries and missing source constraint;
  both fixed with regressions. Legacy receipt during recovery refresh is a known
  session writer: coexistence test DONE/oneTG+oneIG/count1, no extra locks needed.
  Golden12case inputs unchanged; only approved prompt/retry hashes refreshed.
- [x] N37-e: prepare bounded live evaluation and release notes; no paid calls or
  deployment without their applicable explicit authorization.
  Факт:scripts/handoff_review_eval.py defaults dry-run;21synthetic cases need19
  reviews+2mandatory bypasses. Eight runner checks cover reserve/fsync, budget,
  unknown-stop, report reuse and stale catalog rejection. See n37-release.md.
  Repository DOCX is not the current production catalog; fresh read-only capture
  is required before live execution. Paid calls0, production changes0.
- [x] N37-f: execute up to19explicitly authorized review calls on the fresh
  production catalog and synthetic21-case matrix; inspect actions and reply
  facts/links/context manually. Preserve no-sends/no-DB/no-deployment boundaries.
  Факт:19/19budget used,19valid tool envelopes,17expected actions. Fresh read-only
  production text SHA82aa7b12/8tours captured;329100input+5356output tokens.
  Wrong cancel2/10; independent manual audit confirmed context errors14/19/21.
  URLs/factual catalog checks passed, but full primary closing/link-role preservation
  was not established by shortened candidates. No sends/DB/deployment. Original
  report/evaluation plan retained; this run is NOT semantic acceptance.
- [x] N37-g: correct the live-found date/task/context and shared business-rule
  omissions described in n37-review-bugfix.md. Keep original expected actions;
  offline regressions first, no extra paid calls within exhausted19-call budget.
  Факт: trusted business blocks reused without primary transport; explicit-period,
  task preservation, no invented client date and no false promises clarified.
  Evaluator candidates now include canonical closing.1597pytest PASS/8preexisting
  warnings/73.03s, Ruff/diff PASS. Independent read-only composition review PASS.
  Original21expected actions unchanged. At completion of this local correction,
  the revised prompt had no live evaluation yet; subsequent result is N37-h.
- [x] N37-h: after a separate budget, repeat9targeted cases2/4/5/6/8/10/14/19/21
  (5observed failures+4route/format regressions). Check actions and actual facts,
  canonical program links, closing, exact task and preserved client constraints.
  Prepared dry-run plan requires9calls. Separately authorized by «Да, до9вызовов»;
  this repeat starts at0/9, first-run19/19 remains consumed. No deployment.
  Факт:9/9new budget used,9valid tool responses/9expected actions,193457input+
  2778output tokens. Five prior task/decision defects resolved in these cases;
  booking/update/visa/Belostok regressions PASS. Independent manual review and
  data-only assertions: canonical closing9/9 once at end;8URL occurrences/5unique
  all canonical program links from catalog; no false delivery/callback promises.
  Same captured text SHA82aa7b12; source hashes match corrected manifest.
  No substantive blocker in9checked responses. Minor context-shortlist wording
  and link ordering retained as nonblocking observations. Total28authorized calls
  consumed (19+9); no IG/TG sends, production writes or deployment.

| Progress N37 | Status |
| --- | --- |
| N37-a–h | Local implementation/corrections and targeted verification complete |
| Live semantics | Corrected9case repeat PASS; first19call findings retained; total28used |
| Production | Combined N37/N38 deployed29Oct after explicit «деплой»; no manual paid replay |

## Micro N36: manager justification

- [x] N36-a: inspect overlapping instructions and fix the common prompt only;
  remove vague complexity trigger, preserve mandatory priorities and schema.
  Факт: sharedblock once in both countbranches; old subjective uncertainty removed;
  task addressed to manager, company-service facts not delegated to customer.
- [x] N36-b: synthetic semantic cases, unchanged golden inputs, existing route
  regressions, full pytest/Ruff/diff and independent read-only review.
  Факт:1506PASS/8preexisting warnings/70.33s,Ruff/diff PASS;12golden caseinputs
  unchanged. Independent review: tools/JSON×count0/count3 priority construction PASS.
  Clarifying personal-details phrase is scoped to human-manager tasks in context;
  it does not expand the bot's existing own-question rule.
- [x] N36-c: distinguish offline evidence from model semantics; prepare bounded
  live evaluation with no sends/DB changes, execute only with explicit call budget.
  Факт:6authorized calls gave6correct decisions; Wi-Fi context initially assigned
  verification to customer, fixed wording and2separately authorized repeats PASS
  on exact final SHA9cf97fdf. Two nulls (visa alternatives/oldhandoff count3), four
  required handoffs preserved. Runner reserves/fsyncs before sending, rejects
  report reuse and stops on unknown; safety mock checks use0network calls.
- [x] N36-d: report local status; production deployment requires separate consent.
  Факт: packagea9a63300,oneproductionfile prompts.py only, source-only fallback.
  No live-client/TG sends or workingDB writes; no server deployment performed.
- [x] N36-e: explicit «деплой»26Oct authorizes one-source production rollout;
  guarded backup/source-only fallback, restart safety and health/catalog/receipts
  verification. Preserve env, client state, pauses, limits and recovery scope.
  Факт: releasef8120956,remote exactrollbackproof+onlinebackup integrity PASS;
  oneprompt+manifest installed,31SHA PASS. PID11852→3836,start16:36:36.2884592Z
  (19:36:36Minsk),local/publichealth200,catalog8tours/46041chars published.
  Installed tools/JSON×count0/count3 policy smoke PASS without model calls.
  Env/credentials/launchers/allowlist1/baselines retained;560oldsent receipts,
  18terminal jobs,1481sessions preserved,current sent562,pending/unknown/sending0.
  Startup errors/warnings0 atpostflight. DB was not restored; no state resets.

| Progress N36 | Status |
| --- | --- |
| N36-a–d | Local checks complete;8calls used within6+2explicit budgets |
| N36-e | Deployed/verified26Oct,process start19:36:36Minsk |

## Micro N35: ADS text only

- [x] N35-a: trace webhook/recovery/direct boundaries and record the policy before
  code; add regressions proving no ad-media/context/empty escalation.
  Факт:14 initial RED→GREEN; accepted .kiro/decisions/0015-ad-text-only-routing.md.
- [x] N35-b: implement common text-only normalization, defend old queued events,
  replace superseded runtime ad-analysis test expectations without weakening
  security, ordinary media, handoff or delivery checks.
  Факт:32new casesPASS including old claimed empty job ignored/done, both API/
  webhook source orders and independent attachments.40superseded ADS-only test
  functions/98parameter cases replaced with new policy; JSON/privacy/delivery
  checks and pure media utility security retained. Retirement map in artifacts.
- [x] N35-c: focused/full pytest, Ruff/diff, independent read-only review and
  runtime/spec evidence. Production deployment is separate.
  Факт:1496fullPASS/8preexisting warnings/60.12s; Ruff/diff/microPASS and review
  clear. Exactly4source paths differ from installed manifest; no server/model/
  messages. runtime/ad-text-only-routing.md. Deployment not performed.

| Progress N35 | Сейчас | Дальше |
| --- | --- | --- |
| ADS text only | Выложено22Oct20:16:18 Минск;31SHA/health/state проверены | Живой клиентский отклик отдельно не инициировался |

- [x] N35-d: separately authorized code-only deployment after View ad scope
  clarification. Факт:72server isolatedPASS, rollback proofPASS;4sources+manifest,
  PID11436→15408,31SHA/env/credentials/launchers/allowlist1/baselines preserved.
  407prior receipts retained,408current; terminal jobs/session revisions preserved,
  active/pending/unknown0. Installed parser ADStext/user,empty/ignored,ordinaryphoto
  verified, initial logs clear; no manual messages/model calls. Runtime note below.

## Micro N34: placement creatives

- [x] N34-a: record bounded provenance contract and decision; reproduce rejection
  using safe synthetic equivalents of the four live creative shapes.
  Факт: см. .kiro/decisions/0014-placement-ad-provenance.md; 16 initial RED,
  plus 3 expanded-creative RED after real API exposed missing direct permalink.
- [x] N34-b: accept proven canonical placement media, keep clicked image and
  conservative provenance through normal/mixed/shared fallback paths; regressions.
  Факт:29 new cases green; isolated live candidate resolves four originals
  VIDEO/VIDEO/IMAGE/IMAGE with marketing_variant. Production hashes preserved.
- [x] N34-c: focused/full pytest, Ruff/diff, independent read-only review and
  evidence. Production remains unchanged; deployment separate.
  Факт:60 focused PASS;1562 full PASS/8 preexisting warnings/63.84s;
  Ruff/diff/micro validation PASS; read-only review clear. Evidence:
  runtime/meta-placement-media.md. Accepted ADR0014; no model calls or sends.

| Progress N34 | Сейчас | Дальше |
| --- | --- | --- |
| Placement media | Выложено20Oct20:06:34 Минск;31SHA/health/4живыхmedia/296receipts проверены | Точный показанный вариант без селектора не доказан |

- [x] N34-d: separately authorized code-only deployment. Факт: server isolated
  60PASS, guarded rollback PASS;3sources+manifest,PID5380→11436,31SHA/env/credentials/
  launcher/recovery allowlist1/baselines preserved;296sent receipts and terminal
  jobs retained, no queue/unknown or initial post-restart errors. Installed
  resolver proves4actual media without model/sends. runtime/meta-placement-media.md.

## Micro N33: EOF tool arguments

- [x] Доказать границу сбоя: provider arguments оборвались до manager value,
  SDK/logger raw не режут; текущие beta/strict параметры соответствуют docs.
  Схема не объявлена причиной. До кода — bugfix.md, платных вызовов нет.
- [x] 6 EOF SDK/handler RED → GREEN; отдельный reason и доверенный retry,
  ровно две попытки и отсутствие частичного ответа/утечки в prompt.
- [x] Review выявил ValueError на 5000-digit числе: воспроизведение RED → GREEN,
  сохранён прежний validator path. Журнал сохраняет reason/raw приватно.
- [x] Полный QA, review, runtime evidence. Профильный итог 82 PASS;
  полный native pytest 1480 PASS/8 прежних warnings, 55.41 с; Ruff/diff PASS.
  Независимое review закрыто после фикса ValueError. Живая эффективность
  напоминания не проверялась; runtime/deepseek-incomplete-tool-arguments.md.

| Progress N33 | Сейчас | Дальше |
| --- | --- | --- |
| Hardening | По отдельному «деплой» выложено: PID4136/29 SHA/health, EOF smoke PASS; schema прежняя | Живая эффективность напоминания не подтверждена |

## Quick V1 tasks: voice recognition trial (2026-10-10)

- [x] V1gigaam-a: inspect pinned CPU/ONNX inference/model provenance, isolated setup/dependencies checks, existing PCM inputs and production baseline hashes/health; no changes to Whisper or bot runtime. Факт: onnx-asr0.12.0/ORT1.23.2/numpy2.2.6 separatevenv/pipcheckPASS,noTorch; community export officialGigaAM-v3 e2eRNNT FP32 revision322c3b29492673eb7d0b434bfa9dfb8653e34d02,5files892410829bytes SHA/sizeverified. BaselinePCM matches/17prodSHA/launcher/PID2984/localhealthPASS. Bootstrap exitcheck failure→samepinnedpip directrerunexit0; no prod/Whisperdependencychange.
- [x] V1gigaam-b: GigaAM first+two warm runs on matched speech/silence, CPU/RAM/load/disk/private text; additional >25s mechanism and number/date/name control with explicit real/synthetic provenance when available; no invented missing-sample accuracy. Факт:42newruns:15GigaAMdefault+15no-spin+6Parakeet+6turbo controls. GigaAM warmbaseline1.789/.357(default) and2.721/.854(no-spin), CPU~16/25%vs12.4%, after-main1021.9MiB. Shared joinedown43.127s2chunks/TTS45.39s3chunks≤25s coveragePASS. Syntheticphone/date/5days/120EUR/all3tours preserved byGigaAM/turbo; Parakeet«Познань»→«Поздном». Allrepeattexts stable, twoGigaAMmodes same. No natural-long/noise/contacthumanaccuracyclaim.
- [x] V1gigaam-c: meaningful validation/read-only review of results/settings/formulas/quality, report vs existing Parakeet/Whisper, final prod17hash/launcher/listener/health unchanged, spec/runtime cascade; integration V1d stays pending. Факт:78recordverifierPASS(42new+36prior), sourcePCM/chunks/CPU/fullprecision/privateconsistency verified; read-onlyreview confirms formulas/scope and CPU-intensity!=CPU-seconds. no-spin CPUwork18..38%higher vsdefault, runtimeOSwarningServer2019 retained. Reports runtime/gigaam-whisper-parakeet-comparison.md + privateJSON; spec/runtimecascade. Final17SHA/launcher/PID2984 unchanged, local/publichealthok, only normalPython2984/14312 remain,no native listener; finalPSinventoryexit1→samechecksaftermissing-namequeryfixexit0. Appsource/config/data/messages unchanged.

- [x] V1parakeet-a: official portableCPU runtime/Q8 artifact inspection, checksum/setup/version/CLI smoke, existing owner inputs SHA and decode equivalence, baseline17hash/launcher/health. Факт: official NeMo-Speech.cpp0.2.0 Windows CPU ZIP published SHA verified; Q8 model713975456bytes/LFS SHA/revision verified. Own21.439s/native6.912s files converted to identical16kHz monoPCM16, per-input SHA retained; native portable setup isolated, no PATH/system/prod installation. Runtime/model download1.276/63.513s; setup/version/CLI/decode checks PASS. См. runtime/parakeet-whisper-comparison.md.
- [x] V1parakeet-b: same recordings/silence, Parakeet and Whisper small/medium/turbo measured first/warm inference, load, CPU/memory/disk and private transcript consistency; no external STT calls/production changes. Факт:36 runs/4engines/3inputs/first+2warm, no concurrent engines; warm main6.337/6.060/16.563/20.933s and native2.664/4.198/12.382/19.946s. All3texts percase equal, silence empty; CPU about12.5%16logical capacity during speech, distinct peak/post-run RAM and disk recorded. Isolated httpx install/pip check PASS; initial import and loopback precheck errors fixed, same cases PASS. Private outputs retained outsideGit.
- [x] V1parakeet-c: read-only verify measurement formulas/scope, manual quality comparison without false WER, concise full-parameter owner report, source17hash/launcher/health unchanged and spec/runtime evidence sealed. Факт: verifier independently reviewed all36runs/PCM/durations/CPU rounding-bound formulas, PASS. Parakeet3.303x/7.486x faster vs turbo; peakRAM54.43% lower but main post-run snapshots13.61% lower. Quality shows Parakeet missing «с» vs turbo, small wrong «Пух», medium missing noun; no literal reference/WER/phone/noise claim. Report runtime/parakeet-whisper-comparison.md, cascade requirements/design/runtime.17source SHA/launcher unchanged, listener2984 unchanged, local/public healthok, no native trial process remaining. V1d integration remains pending.

- [x] V1download: own-test real Instagram audio URL/download/container+codec proof. Факт: old own message Graph GET200/id+from with no attachments; attachment edge200/empty. Owner explicitly authorized temporary capture+restore restarts. New signed webhook own audio payload.url present; bounded CDN GET200,36384bytes,MIME video/mp4. Actual bytes: MP4/isom, audio-only AAC48000Hz/stereo,6.912s,162 decoded frames; isolated PyAV16.1.0 full decode PASS. SHA256 a62338c52900affc3c9b3146812362f948ef2354d4f780a35f9b5bd9a26287e6. Wrapper12 tests PASS; PowerShell5 array-count check FAIL→fixed same check PASS. Original launcher hash restored,17 source hashes unchanged,new normal listener2984,local/public health ok. Private reports retained outside Git; no raw URLs/transcript printed, no STT/API processing. One observed native recording, not universal codec guarantee. See runtime/instagram-voice-trial.md.

- [x] V1cpu: owner-requested actual CPU load measurement, turbo same owner sample twice; process CPU-time/elapsed/logical-count, report average whole-server CPU share plus measured memory/capacity. Факт:16 logical CPUs, CPU42.797/33.000s vs wall21.435/16.509s →12.48/12.49% total capacity averaged during STT; peak working set1891.8MiB (~11.7%15.77GiB physical). Cached model load4.614s/decode0.045s excluded from STT CPU interval. Input SHA/transcript consistent; syntax/read-only formula review PASS, private CPU report retained. System-wide/peak CPU unmeasured; no production change. See runtime/instagram-voice-trial.md.

- [x] V1a: prior FR-3/schema/batching/guards research + selected trial requirements/design. Факт: owner selected local Whisper; server16 logical CPUs/15.77GiB RAM/10.97GiB free/Python3.12.10; required packages absent; official CPU/INT8/VAD docs read. Audio URL and mixed merge currently unsupported, production unchanged.
- [x] V1b: isolated trial runtime/cache/model + empty-speech smoke;17 production SHA/health. Факт:faster-whisper1.2.1/CTranslate2 4.8.2/PyAV19.0.1 installed only voice-trial-env, pip check green; small CPU/INT8/2 threads/1 worker. First download+load46.186s; cached load2.489s, peak working set706.2MiB. Three-second silence produced0segments/0chars (0.066s); this is NOT speech latency or accuracy. Production17 SHA unchanged, public health ok, no restart/AI/manager/client calls.
- [x] V1c: user speech sample comparison + load/warm latency/working-set measurements. Acceptance: report actual sample content fidelity and measured times before integration; dates/numbers only if present. Факт: owner M4A21.439s, small5.497/6.146s (initial6.584s)/706.6MiB, medium17.240/16.273s/1767.1MiB, turbo17.268/18.282s/1908.0MiB; repeats equal per model. Turbo preserves tour/Warsaw/mother/separate program meaning, recommended candidate; no literal reference/WER/dates/phone claim. Turbo cache load5.615s, silence0chars/0.065s. Input SHA matches owner file for small/turbo. Owner confirmed file differs from earlier visa text. PyAV19 real-file decode FAIL→pin16.1.0 exact same M4A PASS/pip check PASS; syntax/diff check/read-only review,17 remote source SHA/health unchanged. See runtime/instagram-voice-trial.md; private sample/report artifacts outside Git.
- [x] V1d: finalize integration bounds/schema/test matrix after trial; voice+text+visual one-call batching, silence/error/takeover/duplicate/CDN regression, staged QA/rollout. Факт: V2 implementation and authorized production rollout complete;709PASS/native worker+actual application client+production smoke/source/env/launcher/local+publichealth PASS. Owner live voice remains V2f; see runtime/gigaam-voice-integration.md.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| V1 | Native download + matched GigaAM/Parakeet/Whisper78-record comparison verified; GigaAM current candidate, CPU modes/OS/longform caveats explicit, production unchanged | V1d: production voice integration/schema/limits/tests and real recognition proof |

V1c comparison extension before code: medium17.240/16.273s,1,767.1MiB, repeat text equal; initial noun omission. Evaluate turbo same settings, preserve per-repeat raw text/input SHA/decode timing, warmed small repeat for complete measured comparison. No voice production enablement yet.

## Micro N6 tasks (2026-10-10)

- [x] N6a: regression red→green, краткий manager Context/prompt + bounded fallback. Acceptance N6.1–N6.3. Факт:18 initial FAIL→PASS,2 URL/consultation FAIL→PASS,1 link-label FAIL→PASS;116 engine/phone PASS,654 full local PASS/Ruff/diff-check PASS; read-only final review clear,15 new integration/prompt cases, один AI и unchanged history/source phone.
- [x] N6b: full local/server QA, read-only review, guarded deployment/backups/SHA/health/docs. Acceptance N6.4. Факт:654 local PASS/652 server PASS+2 previous JPEG-artifact skips/Ruff/diff-check PASS, final review clear; backup-contact-summary,3 files/all17 SHA verified, PID15292→12324, local/public health200/ok, media flags true. Docs sealing with unchanged sessions/config/limits; no extra paid calls or manual sends.
- [ ] N6c: live short summary повтор владельца. Факт: ожидается после rollout; N5 live feedback подтвердил нежелательную длинную выдержку.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N6 | Deployed: local654/server652+2 prior skips;17 SHA/health ok | Optional new live owner escalation |

- [x] N5a (N5.1–N5.3): paired delivered answer + human media context, phone isolation/priority/limits, regression tests. Факт:8 initial FAIL→PASS;3 no-caption/source review FAIL→PASS;12 new integration cases,101 engine/phone PASS. См. runtime/instagram-contact-context.md.
- [x] N5b-local (N5.4): full local QA/read-only review/spec/docs/runtime/manifest/package. Факт:639 full PASS/Ruff/diff-check PASS, final review clear, contact-context package2 files/17 SHA prepared; actual input phone and unchanged history verified, no extra AI.
- [x] N5b-server (N5.4): isolated server QA/guarded patch/restart/health/docs. Факт: server637 PASS+2 prior JPEG-artifact skips/Ruff PASS; access restored/upload exit0, backup-contact-context,2 files/all17 SHA verified, PID5292→15292, local/public health200/ok, three flags true. No sessions/config/limits/dependencies/paid replay mutated.
- [x] N5c: live feedback владельца: слишком длинный ответ вместо выжимки. Факт: новая просьба N6; формат N5 superseded N6, прежняя выкладка отражена честно.

- [x] S7a (S7.1–S7.4): regression live25s gap → one-shot bounded exact context, без ответа на reaction; MID/flags/manager/media/snapshot coverage. Факт: original4 FAIL, review merge2 FAIL/contact2 FAIL → PASS;26 new cases, full local627 PASS. См. runtime/instagram-story-reaction-context.md.
- [x] S7b (S7.5): full local/server QA, read-only review, spec/docs/runtime/manifest; guarded patch и health по существующей авторизации. Факт: local627 PASS/server625 PASS+2 previous JPEG skips/Ruff/diff-check PASS; read-only final review clear; backup-story-context, 4 files/17 SHA verified, PID10076 → 5292, local/public health ok. No paid calls/data/config/limit changes; decisions CLI отсутствует, решение зафиксировано в design до кода.
- [x] S7c: новая живая reaction + отдельный вопрос владельца; без ручного paid replay или сброса test session. Факт: владелец 2026-10-10 подтвердил reaction→«можно подробнее»→бот распознал Эльбрус; предоставленная контактная эскалация содержит тот же exact VIDEO story ID. Это подтверждение владельца, не новая ручная API проверка.

- [x] M2a (M2.1–M2.5): регрессии → mention/direct video, accurate media provenance, GIF ignore, file/product handoff. Факт: initial12 FAIL → PASS; local601 fullPASS, 42 additional cases. Типы на все output frames; история по input index/format; GIF и file/story precedence regressions PASS. См. runtime/instagram-incoming-video.md.
- [x] M2b (M2.6): full local/server QA, native local VIDEO decode, read-only review, docs/runtime/manifest и guarded rollout. Факт: local601 PASS/server599 PASS+2 previous JPEG skips/Ruff PASS; native actual MP4→20 frames, no paidcalls; review без оставшихся дефектов; backup-visual, 8 files/17 SHA verified, PID3460 → 10076, local/public health ok. scripts/validate_micro.mjs/decisions.mjs отсутствуют; existing pipeline reuse без установки инструментов.
- [ ] M2c: optional live mention VIDEO/direct VIDEO владельца. Факт: ещё не получены; native/synthetic tests не выдаются за Meta delivery.

- [x] A2a (A2.1–A2.4): regressions → resilient parser, unsupported/unknown fallback, visible postbacks, honest notification failure/takeover. Факт: 24 initial FAIL → 44 regression PASS, full local 559 PASS/Ruff PASS; final read-only review без дефектов. См. runtime/instagram-attachment-fallback.md.
- [x] A2b (A2.5): full local/server staged QA, read-only review, docs/runtime/manifest и guarded rollout. Факт: local559 PASS/server557 PASS+2 previous JPEG skips/Ruff PASS; backup-attachment, 3 files/16 SHA verified, PID11672 → 3460, local/public health ok. scripts/validate_micro.mjs отсутствует, контракт проверен meaningful pytest и review. См. runtime/instagram-attachment-fallback.md.

2026-10-08. Последовательность T1 → T2 → T3 → T4; rollout после T4.

- [x] T1 (S1,S4,S6): безопасный story metadata, отдельный media service и Windows decoder; проверка ID, загрузки, формата, лимитов, 10 кадров и cleanup. Факт: story_media.py/decode_story_media.ps1, реальные 10 кадров 720×1280 собственной истории и native IMAGE test PASS.
- [x] T2 (S2,S3,S5): vision factory, мультимодальный HumanMessage, флаг, интеграция с сессией/guard/очередью/перехватом. Один AI-вызов, без повторов и утечки изображений в БД. Факт: get_vision_llm payload и mock AI integration tests PASS.
- [x] T3 (S1–S6): meaningful unit/integration tests, реальный Windows decoder на собственном видео; read-only review и устранение замечаний. Факт: 54 media tests PASS; два read-only review, учтены очередь/перехват, отмена декодера, порядок вопросов и batch stories.
- [x] T4 (S1–S6): полный pytest/Ruff, обновление архитектуры и статуса requirements; подготовить точный список файлов/откат для rollout. Факт: полный pytest 343 PASS, Ruff PASS; docs/ARCHITECTURE.md, docs/DEVELOPMENT.md, rollout.md и runtime-manifest.json.
- [x] T5a (S5): rollout по явному запросу «деплой». Факт: 12 SHA совпали, backup старых файлов/.env, server pytest 401 PASS/2 JPEG skips, Ruff PASS; native server VIDEO/IMAGE/VIDEO → 21 изображение; три флага true, listener 5512 → 15384, localhost/public health 200/ok.
- [x] T5b (P1–P5,R1): реальный native Reels и общий vision-ответ. Факт: повторная отправка владельцем → ig_reel/reel_video_id → 10 кадров → один vision 32617 input/259 output → Instagram message.sent, 14.4 с; история без media URL/base64.
- [x] T5c-image-story (S5): live IMAGE own story vision. Факт: 2026-10-08 20:34 UTC, IMAGE → 1 изображение → vision 27317 input/261 output → Instagram message.sent.
- [ ] T5c (S5,I1–I3,P1–P5): live VIDEO own story/обычного фото/фото-поста/смешанной карусели. Share carousel пока post_unavailable до AI; native decoder и mock проверки зелёные.
- [x] I1 (I1,I3): image metadata и безопасная склейка captions/photos/MID внутри webhook, прежние story/post/unsupported пути. Факт: фильтрация отдельных MID до merge; partial retry/new text/photo и оба порядка post/photo PASS.
- [x] I2 (I2,I3): prepare_images + original vision singlecall, без подписи/отказы, отдельный флаг, text-only история и общие guards. Факт: mock singlecall/original, caption/no-caption, guard/manager/failure/cleanup PASS.
- [x] I3 (I1–I3): meaningful tests, JPEG/PNG native decoder, full pytest/Ruff, обновлённые docs/manifest/rollout. Факт: настоящий JPEG/PNG decoder PASS, JPEG byte equality, полный pytest 378 PASS, Ruff PASS, read-only review после устранения двух P2.
- [x] P1 (P1,P5): shared payload metadata, lossless shared/text merge и MID, независимый флаг. Факт: ig_post/share fixtures и legacy/off PASS; live shared webhook отдельно не проверен.
- [x] P2 (P2,P4): точный Graph resolver и IMAGE/VIDEO/carousel preparation, исключить cover-as-Reel и partial carousel. Факт: Graph собственного Reels и 7-element IMAGE/VIDEO carousel; реальный Reels → 10 кадров 0.000–8.500 с; exact ID/permalink, thumbnail-only, incomplete carousel и cleanup PASS.
- [x] P3 (P3,P5): один original vision-вызов, подпись/no-question, безопасная история, guard/manager/queue/fallback. Факт: mock integration PASS, подписи и кадры имеют номер публикации; unavailable не вызывает AI.
- [x] P4 (P1–P5): regression/integration tests, разрешённый read-only media probe, полный pytest/Ruff, docs/manifest/rollout. Факт: полный pytest 403 PASS, Ruff PASS; read-only review закрыл оба P2, runtime/windows-reel-last-frame.md и reel-preparation-check/evidence.json. Rollout закрыт T5a, live Reel T5b; другие live media T5c.

| Progress | Факт |
|---|---|
| Спека | Requirements/Design/Tasks оформлены до кода; согласованный узкий Quick Spec без промежуточных гейтов |
| Реализация | T1–T4, I1–I3 и P1–P4 завершены локально: own story, JPEG/PNG, mention VIDEO, direct VIDEO, доступные Graph posts/Reels/carousel; voice/OCR исключены |
| Проверка | N6: local654 PASS/server652 PASS+2 previous JPEG-artifact skips/Ruff/diff-check PASS,15 new integration/prompt cases/read-only review clear; no paid replay |
| Production | N6 deployed: backup-contact-summary/3 files/all17 SHA/PID12324/local+public health ok. N5 live format rejected; N6 short summary owner repeat optional. Mention/direct VIDEO/N4 repeats remain separate |

- [x] R1 (R1): regression реального ig_reel, минимальный type fix и safe identity diagnostics; флаг off и mixed не менять. Факт: 2 FAIL до → 7 PASS после, URL не логируются; full local 408 PASS/Ruff PASS.
- [x] R2a (R1): server pytest/Ruff и guarded patch. Факт: server 406 PASS/2 JPEG skips, backup-reel, 12 SHA verified, listener 15384 → 4388, три флага true и local/public health 200/ok; runtime/instagram-ig-reel-route.md.
- [x] R2b (R1,T5b): новая живая проверка после повторной отправки. Факт: точный native ig_reel успешно получил 10 кадров, vision answer и отправку; старый payload не replayed.
- [ ] C1: окончательно связать исходную ошибку share с конкретным source identity. Факт: permalink владельца подтвердил exact parent/7 children; original webhook URL не восстановлен. Child asset gap воспроизведён отдельно и исправлен C2, ждём live repeat с safe diagnostics.
- [x] C2: exact child/native asset → полный parent resolver; constraints и safe diagnostics. Факт: 7 regression FAIL до → 8 PASS после, IMAGE/VIDEO direct-child не превращаются в partial пост; два actual child ID → exact parent/7 children. См. runtime/instagram-carousel-child-asset.md.
- [x] C3: устранить IMAGE pixel pipeline enumeration. Факт: та же native карусель 25 original изображений 79.6 → 12.6 с без AI; shared 38 PASS, server full 414 PASS/2 JPEG skips, Ruff PASS; лимиты неизменны.
- [x] C4a: guarded server patch/backup/hash/restart/health. Факт: три файла, backup-carousel; 12 SHA verified, PID 4388 → 8160, local health ok, три флага true.
- [x] C4b: live повтор карусели. Факт: владелец сообщил «работает» после повторной отправки; это пользовательское подтверждение, отдельные vision/token logs этой отправки не измерены.
- [x] N1: телефонная карточка/phone postback normalization, phone text/card dedup/MID и safe shape diagnostics. Факт: 23 phone tests PASS, включая generic-card guards, story/referral/MID, shared merge и два последовательных webhook; original template reread is_unsupported=true, raw shape требует live проверки.
- [x] N2: unclosed/malformed marker cleanup и extraction/notification/history/empty fallback. Факт: red 6 FAIL/1 PASS → engine 31 PASS; незакрытый блок извлекается, actual input phone попадает notifier даже без model phone field, старый assistant block очищен в prompt-copy.
- [x] N3a: full pytest/Ruff, manifest/backup/server QA и guarded restart/health. Факт: local 449 PASS, server 447 PASS/2 JPEG-artifact skips, Ruff PASS; backup-phone, 14 SHA verified, PID 8160 → 13928, localhost/public health 200/ok. См. runtime/instagram-phone-card-marker.md.
- [x] N3b: live phone/card после N2c, 2026-10-09 01:44 Минск. Факт: новый normalized phone отличается от всех предыдущих; через 1.35 с nested generic.elements=[] → empty_duplicate/ignored_duplicate, второй AI/non-text handler не запущен. Source logger model_phone_present=false → current input; Telegram sent четырём настроенным получателям, одно Instagram message.sent, latest assistant 75 chars без marker; escalation_count 1→2, manager_last_at=null. Raw payload/уведомления/номера не выводились. См. runtime/instagram-phone-card-marker.md. Предыдущие этапы: flat schema недостаточен; разрешённый two-field test reset с backup/history preserved; 22:15 typed phone no-marker породил N2b, old-context report породил N2c.
- [x] N1b: live payload.generic wrapper и empty nested template correlation с recent phone-only text; regression → guarded patch. Факт: 3 FAIL/4 PASS → green; full local 457 PASS, server 455 PASS/2 JPEG-artifact skips/Ruff PASS; backup-phone-nested, 14 SHA verified, PID 13928 → 8992, local/public health 200/ok. Synthetic guards сохраняют question/ambiguous/unrelated template, webhook integration проверяет один вызов с отдельными POST и retry MID.
- [x] N2b: actual input phone без AI marker → deterministic notifier и короткий phone-only ack по факту success/error/limit. Факт: red 3 FAIL → green; no-marker plain/card/question success/error/limit 9 PASS. Read-only review current-question issue red 2 FAIL → green. Local final 466 PASS, server 464 PASS/2 JPEG-artifact skips/Ruff PASS; backup-phone-notify/backup-phone-context, 14 SHA verified, PID 8992 → 5048 → 16256, local/public health ok. Final live N3b ожидается.
- [x] N2c: смена телефона → согласованный notification context/current contact; old model phone/context и prior mixed phone не переопределяют новый. Факт: marker/no-marker plain/card и old contact/name с budget/date — red 4 FAIL, затем review red 8 FAIL/4 PASS → green 12 cases. Local 478 PASS, server 476 PASS/2 JPEG-artifact skips/Ruff PASS; backup-contact-source-v2, 14 SHA verified, PID 16256 → 2664, local/public health 200/ok. Старый initial contact-source stage не deployed. Review подтвердил исправление. Новый live повтор N3b PASS; точный section старого Telegram не восстановлен. БД/лимит N2c вручную не менялись.
- [x] N4a (N4.1–N4.5): воспроизвести general text + empty template; внедрить fixed sender collector, удалить temporal template/cache/fallback обходы, сохранить media/MID/takeover/current contact. Факт: red before processing started too early → regression PASS; live incident log interval 1,16 с/empty generic/second escalation подтверждён read-only. Новый raw+stateless merge, fixed 5-second collector; старый phone cache и AI timestamp suppression удалены.
- [x] N4b (N4.1–N4.6): meaningful regressions, full pytest/Ruff, read-only review и docs/runtime/manifest. Факт: full local 500 PASS/Ruff PASS/diff-check PASS; async tests обе очередности/текст с телефоном/все MID/разные sender/new batch during AI/manager cancel/media IDs, реальное 5-second окно. Review date/budget, mixed legacy MID и takeover error замечания исправлены и защищены тестами; повторный review без серьёзных замечаний. См. runtime/instagram-template-batch.md.
- [x] N4c (N4.6): guarded server stage QA, backup/apply/hash/restart/health. Факт: server stage 498 PASS/2 JPEG-artifact skips/Ruff PASS; backup-batch, 8 files applied, 15 SHA verified, listener 3964 → 11532, local/public health ok. БД/.env/лимиты не менялись; ручных paid calls/messages нет.
- [ ] N4d (N4.6): реальный повтор текста с номером + automatic template. Факт: запрошен после выкладки; синтетический collector не выдаётся за live evidence.

- [x] M1a: classified story_mention/image metadata, lossless batch merge и vision/history marker. Факт: image_types сохраняет позиции URL/MID и union types; original vision получает marker у нужного image block, system/history пометки без URL/base64. Red → green: 15 targeted mention regressions PASS.
- [x] M1b: regression/full pytest/Ruff/review/docs/runtime/manifest и guarded rollout. Факт: local 515 PASS, server 513 PASS/2 JPEG-artifact skips, Ruff/diff check PASS; read-only review без дефектов. Backup-mention, 5 файлов/15 SHA verified, PID 11532 → 11672, local/public health ok. БД/.env/лимиты не менялись, ручных paid calls/messages нет. См. runtime/instagram-story-mention-image.md.
- [ ] M1c: live mention-повтор владельца. Факт: ожидается после rollout.

## Micro V1 cleanup tasks (2026-10-10)

- [x] V1cleanup-a: подтвердить bounded inventory/bytes/reparse/процессы, сохранить private reports вне сервера, зафиксировать SHA production/GigaAM/аудио до удаления. Факт:27targets4679818142bytes и8exclusivepipcache20373788bytes, reparse отсутствуют; 6582protectedSHA/17prodmanifest/PID2984+14312/local+publichealthok. 27privateevidencefiles downloaded/hashverified locally, archiveSHA97C1F2F4182E7229981029E392D950B41DC24120E3B86C2C4BE09B50C45049D2. ОбщийHFembedding/PyTorch/ORT production сохраняются.
- [x] V1cleanup-b: удалить проверенные Whisper/Parakeet модели, runtimes, helpers и относящиеся cache records; проверить отсутствие targets, GigaAM offline smoke/pip check, SHA/health/PID и записать размер/границы. Факт:27targets+8cache files4700191930logicalbytes removed; no remainingexclusiveSTT wheel/metadata, exportedserverarchive/evidence removed. GigaAM offline voice/silence/pipcheckPASS,6582protectedSHA/17prodmanifest/launcher/.env/inputs unchanged, PID2984/local+publichealthok. WindowsPS5 value/Count serialization fixed in reader; new smoke int16 rejected→float32 normalization→same speech/silence checksPASS; verification-only rerun after deletion, no repeat destructive action. Read-onlyreview confirmed no protectedoverlap/sharedpurge; allintermediateancestors postcheckPASS. См. runtime/gigaam-server-cleanup.md.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| V1 cleanup | Complete: GigaAM selected, other STT trials removed; evidence/6582SHA/smoke/health verified | V1d: GigaAM production voice integration, pending |

## Quick V2 tasks: incoming GigaAM voice integration (2026-10-10)

- [x] V2a (V2.1–V2.2): parser metadata and ordered voice/mixed batch, flag-off/MID/template/GIF/barrier regressions. Факт: ordered audio+text+images/story/mention/MID, off/missing URL, actual empty-generic and unknown/file/product story barriers tested; legacy collector/Instagram regressions/full suite PASS.
- [x] V2b (V2.3,V2.5): isolated resident worker/downloader/config, decoder/chunks/queue/protocol/timeout/cancel/shutdown tests; verify real saved native inputs without AI/messages. Факт:23 service testsPASS; real pinned worker6cases and application-client proofsPASS, model5SHA/native AAC/M4A/duration coverage/resident reuse/error restart/temp cleanup/close verified, pipcheckPASS. Only isolated PyAV16.1 installed; no alternative engines returned.
- [x] V2c (V2.2,V2.4–V2.6): single AI mixed input, fail→manager immediately, takeover/guards/contact priority/brief history regressions. Факт:32 parser/main testsPASS; failure handoff has≤450 human context/noAI/no invented phone/honest notification failure+contacts; unique explicit current phone overrides model, ambiguous model-only phone suppressed; mixed original/mention prompt and history preserved.
- [x] V2d (V2.7): full QA/read-only review/docs/spec/manifest; server isolated proof and concrete guarded rollout/rollback readiness. Факт: full709PASS/Ruff/diff checkPASS; final read-only review no must-fix; staged11-file manifest+eight-file guarded apply artifact/backup+rollback plan/native+client proofs/17-production-source+listener2984/local+publichealth preflightPASS. См. runtime/gigaam-voice-integration.md; production source/env/DB/launcher unchanged.
- [x] V2e: authorized production rollout. Факт: explicit «Да, выложить и включить»; eight bounded runtime files+three voice settings, checksum-verified backup/apply, scheduled RestartTravelBot, listener2984→7116. Actual deployed-client native two-input/silence/cleanup proof PASS; nine applied source/env SHA, unchanged unrelated deployed source/launcher, local+publichealthPASS. No production packages/DB/takeover/limits resets or manual AI/client/manager calls. Backup/rollback integrity strengthened after review before applying.
- [x] V2f: owner live voice through Instagram. Факт: новая запись владельца 2026-10-10 14:16UTC: голосовое распознано, вопрос про Сербию сохранён с voice marker, ответ отправлен14:16:40Z, служебный менеджерский блок отсутствует, manager_last_at=null. Обнаруженная ранняя собственная echo→takeover гонка воспроизведена/исправлена отдельно до повторного теста:714PASS/Ruff/review/20sourceSHA/env/launcher/local+publichealth, listener14396. Только разрешённый test pause reset: history/escalation_count3 preserved. См. bugfix.md и runtime/instagram-early-echo-takeover.md.

Dependency: V2a+V2b → V2c → V2d. V1d is satisfied by V2 implementation/verification, not by prior trials.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| V2 | Complete: production enabled,714PASS,55 voice+5 early echo tests; native/client/deployed smoke and live owner Instagram voice PASS;20 source SHA/env/launcher/local+publichealth, listener14396 | Ordinary operation; real manager messages still enable takeover |

## Quick N7 tasks: честное подтверждение эскалации

- [x] N7a (N7.1–N7.4): red reproduction ложного подтверждения при count3/no marker и общем notify failure; корректный sent/plain/phone/voice/non-text text и история/счётчик. Факт: initial22FAIL/1PASS→green; дополнительные review cases6FAIL→green, claim+question2FAIL→green; итог38handoff +2voice regressions PASS.
- [x] N7b (N7.1–N7.5): минимальный finalizer/outcome и согласованный prompt, Telegram actual receipt/partial semantics, ошибки без credentials/payload, meaningful regressions. Факт: четыре outcomes, текущие подтверждения/обещания отсеиваются, useful clause/URL/question/footer/history сохранены; HTTP200+ok is True, partial-before/after/all-fail/transport credential redaction проверены; prompt neutral+limit priority/cache tests PASS. См. runtime/telegram-handoff-receipt.md.
- [x] N7c (N7.6): full pytest/Ruff/diff-check/read-only review, server guarded backup+3 source hashes/manifest/env/launcher/health/mocked proof; обновить evidence/status. Факт:754PASS/8existingwarnings, Ruff/diff-checkPASS, read-only review clear; three runtime files deployed, backup-v2 SHA verified,21manifest entries/env/launcher verified, listener14396→2416/local+publichealthok. Deployed source mocked proof4outcomes+2Telegram receipts+partial PASS, no external messages/AI/production DB writes. Initial backup guard stopped before source mutation because notifier was absent from old20-entry manifest; old notifier independently hashed, guard repaired/rerunPASS before rollout.

Dependency: N7a→N7b→N7c.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N7 | Complete:754PASS/Ruff/review, deployed3files/21SHA, actual deployed mocked proof/local+publichealthPASS | Ordinary operation; new live message from owner is optional additional evidence |

## Quick N8 tasks (2026-10-11)

- [x] N8a: delegate3 read-only investigations and record screenshot/code/production evidence. Факт: exact story_mention and unsupported_type13:24Z, Graph old invite has no attachments; adtitle07:35Z, exact permalink unavailable/Marketing400; conflicting tourism-only cooperation prompt. No source/data/settings mutations in probes.
- [x] N8b (N8.1): red→green silent mention/parser/collector/handler guards, no client send on any outcome; ordinary neighboring requests preserved. Факт: parser priority/raw mixed/MID,5outcomes/username failure/echo guards PASS; deployed mocked silent4outcomes PASS.
- [ ] N8c (N8.2): prove invitation discriminator and only then route it silently. Факт: pending; owner rejected all unsupported_type. No guessed classifier allowed.
- [x] N8d (N8.3–N8.4): preserve bounded referral/title/private available visual sources through all merges/AI/history, exact source guards/no guessed ad_id, meaningful regressions. Факт: title/photo/voice/replacement/different sources/original labels/private history/exact ID tests PASS; exact full ad video remains unproved by access probes.
- [x] N8e (N8.5): cooperation business prompt exception/clarification/marker policy and honest outcome regressions. Факт: prompt media-intent and sent/failed/limit tests PASS; deployed prompt proof PASS, no live paid AI call.
- [x] N8f (N8.6): full QA/read-only review, guarded bounded rollout/backup/manifest/env/health/server mocked proof, runtime/docs/status with pending limits. Факт:791PASS/8existingwarnings/Ruff/diff-check/3reviews;3runtimefiles/backup/21SHA/env/launcher/PID2416→11352/health/deployed no-network/no-DB mocked proofPASS; incident and remaining limits recorded in runtime/instagram-business-context.md.

Dependency: N8a→N8b/N8d/N8e→N8f; N8c depends on real discriminating data, not broad fallback.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N8 | Known routes deployed and checked;791PASS/3reviews/21SHA/health/mocked proof | Invite discriminator pending; exact full ad video unavailable with current access |

## Quick N9 tasks (owner clarification, before code)

- [x] N9a: restore N7 action/security/escalation/media policy; general grammar/meaningful phrase prompt. Факт: N7 BASE equal except one style rule, SECURITY/ESCALATION/ACTION equal, исходная media instruction restored; cooperation override removed.
- [x] N9b: policy equality/prompt variants/receipt tests and QA/read-only review; guarded1file rollout/backup/manifest/health/deployed mock proof. Факт:5red→75targetedPASS/794fullPASS/8existingwarnings/Ruff/diff-check/review;1prompt file backup/21SHA/env/launcher/PID11352→8928/local+publichealth/deployed mocked policy equality/known routes proof PASS, no paid AI/external messages/productionDB writes.
- [x] N9c: docs/runtime/spec status correction; distinguish prompt instruction from live generation guarantee. Факт: docs/runtime исправлены, N8 cooperation policy помечена отменённой; живой wording после новой инструкции не выдаётся за проверенный.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N9 | Correction deployed; policy restored, common style instruction,794PASS/health/proof | Live wording optional verification; model instruction is probabilistic |

## N10 discovery

- [x] N10a: official documentation route/token/media evidence; inspect existing granted access without auth changes. Факт: debug_token200/typePAGE/valid/matchesapp+page,8scopes безads_read/ads_management; exactad400/code100/subcode33. Agent official Context7/SDK25 маршруты ad→creative→original video/image проверил. Permissions/adaccounts edges отсутствуют уPAGE node, это не доказательство отсутствия рекламного аккаунта у человека.
- [x] N10b: bounded exact permalink archive lookup beyond previous300 items; verify actual media availability if found. Факт:8pages/767items/archive exhausted/oldest2015-10-04; exactDeI-3NiA_5L не найден. Только список, не анализ/скачивание соседних файлов. Это доступный published media list, не вся реклама/архив/удалённое.
- [x] N10c: concrete recommendation/evidence/current access limits and next required step; no speculative success claim. Факт: рекомендован отдельный User/SystemUser ads_read adaccount token, messagingPAGE unchanged; original asset GET ещё требует нового доступа/проверки. Альтернатива registry точного ad_id→исходник из AdsManager. Новых auth/settings/runtime изменений не было.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N10 discovery | Access blocker established; full accessible767-item list checked; official exact-source route found | Separate authorized advertising access needed to test actual current ad original; no source obtained yet |

## N10 authorized access

- [x] N10d: official Meta UI login/app inspection and separate ads_read-only grant for the correct account. Authorization: explicit owner reply «Да, настроить доступ только на чтение». Preserve PAGE credential/campaigns; report actual granted scope separately from intent. Факт: owner confirmed saved profile and completed emailed verification; separate Employee Sundita Reader61595313984712 with exact adaccount2748504208879634 ANALYZE and app1133220645701291 TEST verified. Token issued after ads_read/60-day selection; live /me/permissions returns only ads_read+public_profile. No DEVELOP/MANAGE or campaign writes; new credential isolated in private official Meta/Explorer handoff tabs, not server config.
- [x] N10e: exact ad→creative→original video probe and safe evidence, credential isolation/account check. Факт: new token v26.0 exact ad/account/creative/permalink proof; FBvideo.source code10. Existing PAGE v25.0 effectiveIG17947642536299061 exact supplied permalink→VIDEO/media_url→valid MP46595346bytes/26.966667s→10nativeoriginal JPEGframes/noaudio. Source IG mismatch rejected before download. Final probe exit0/local MP4 SHA equals server/read-only review; env/launcher/21runtimefiles unchanged/localhealthok. First manifest-shape failure and CreateNew rerun collision diagnosed/fixed; final same probe green. Evidence: runtime/instagram-business-context.md and exact-ad-ig-source-20261011.json; no automatic bot routing/deployment yet.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N10 setup | Complete: actual read-only scopes/account verified, full exact ad MP4 and10frames retrieved | Automatic resolver/configuration/deployment is separate work; no universal media-access guarantee |

N10 audit: initial auto-review identity rejection resolved by owner's explicit saved-profile confirmation. Another account-card read was rejected; no retry/grant to that account, exact Ads Manager filter proved correct Сандита Б. Personal generator warning about revoking prior permissions was respected, generator not used. First system-user name rejected; accepted Sundita Reader, no duplicate. TEST made ads_read visible empirically; no broader app role needed. Meta verification completed by owner; token created and API tested. Exact video proof uses effective Instagram media via existing Page access; source ID has a different permalink and FB video node denies source. Neither fallback is guessed. New token remains in official private handoff tabs; production feature/configuration unchanged.

## Quick N11 tasks

- [x] N11a (N11.1/3/4): separate exact ad resolver/config/private credentials, account/permalink guards, bounded safe errors, meaningful red→green MockTransport tests. Факт: dedicated ad_media resolver and meaningful identity/account/expiry/credential-isolation tests pass.
- [x] N11b (N11.1/2/3): connect ad visual part/decoder/main, preserve voice/customer media/abort/order/onevision, honest fallback/regressions. Факт: 128 targeted tests PASS; combined voice/photo/ad request and takeover/failure routes verified.
- [x] N11c (N11.4/5): startup credential health/docs/fullQA/read-onlyreview, safe server artifact proof and credential/rollout preparation. Факт: 813 full pytest PASS, Ruff PASS, diff-check PASS; source review clear. Helper review findings corrected and isolated absent/partial/complete rollback and accepted-socket timeout checks PASS. Server read-only preflight: 21 baseline files, 4 staged files, production unchanged.
- [x] N11d (N11.4/5): required action-time lifetime/credential approval, actual isolated token persistence, guarded rollout/rollback/manifest/runtime/health/source proof without client sends/paidAI. Факт: owner approved never-expiring ads_read and private server persistence, completed Meta emailed verification. Actual debug_token validates app/scopes/expires_at=0; credential stored in separate private gitignored file. Guarded apply exit0/backup verified; verify exit0/22 manifest hashes/success-failure-takeover mocks/exact video/10frames/caption617; public health enabled=true/ready=true. Messaging credentials and client state preserved.

Dependency: N11a→N11b→N11c→N11d.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N11 | Deployed and enabled; 813 pytest/Ruff/review/server 22 hashes/public health/exact video and 10frames verified | Optional new real client ad reply; Meta may revoke access despite expires_at=0 |

## Quick N12 tasks

- [ ] N12a (N12.3): safe incident log/API reproduction and approved Reader grants К/С; prove actual exact ad owner/source availability.
  Факт частичный: approved ANALYZE-only grants assigned and /me/adaccounts returns Б/К/С. Exact incident ad remains400/code100/subcode33; exact ad.id filtering returns200/empty in all3. Owner/source not established; requested cabinet or View ad link, no claim of successful incident recognition.
- [x] N12b (N12.1/2): strict compatible multiaccount config/resolver/health, meaningful legacy/allowed/foreign/malformed/duplicates/inaccessible regressions, exact same media guards. Факт: 31 resolver tests PASS, full825 pytest PASS/Ruff PASS/diff-check PASS; read-only source review clear. CSV max10 ASCII numeric IDs, legacy compatibility/dedup/all-account health/foreign rejection before creative verified. Pytest collection explicitly limited to tests, preserving private credential ACL and all prior813 tests.
- [x] N12c (N12.4): full QA/read-only review, guarded rollout/backup/source proof/health/manifest, update evidence; no client state reset or sends. Факт:825pytest/Ruff/diff-check PASS; source/helper read-only review clear. Staged/after-deploy live access3accounts/known exact ad video10frames PASS; apply/verify exit0, private backup verified,22runtime hashes, PID/starttime changed13396→14524, local/publichealth enabled/ready. Source proof invokes no paid AI/client sends; handler success/failure/takeover mocked. CIM denied for server identity check; bounded native netstat+Get-Process replacement and same preflight PASS. Stable identity before/after health prevents old-process false-green. Incident media remains unavailable.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N12 | Three-account support deployed;825tests/Ruff/review/22hashes/newPID/publichealth/source proof PASS | N12a owner/source still unresolved: incident exact ad100/33 and filtered lookup empty in all3; awaiting cabinet or View ad link |

## Micro N13 tasks

- [x] N13a: exact publication/read-only incident evidence; reproduce photo-before-referral split. Факт: shared source17943390366326685 GET200/IMAGE matches exact Dci_ZT0s-3b; caption0. Published archive767 excludes post, direct supplied identity works.18:34:45 shared/18:34:46 visa question ADS/2→2dispatch/one prepared image+answer then ad_graph_unavailable+Telegram+secondanswer. No source guessing.
- [x] N13b: minimal order-symmetric segmentation fix and full incoming post preference/fallback regressions, preserve different explicit ads/silent boundaries/allMID/fallback/guards/history. Факт: first3order tests red then green; source4outcomes red then green; review found guards/history,4red regressions fixed. Full840pytest PASS/Ruff PASS, new15cases, no real network/DB/AI/messages.
- [x] N13c: QA/review, guarded two-file rollout/backup/new-process health, document actual limitations without client replay/reset/sends. Факт:842fullpytest/Ruff/diff-check PASS,17newcases; read-only review guard/history/partial-source findings fixed with red regressions. Two-file apply/verify exit0/private-state-free backup/22runtime hashes/env credentials unchanged; PID14524→12560 confirmed around health read, publichealth ready. Actual exact Dci_ZT0s-3b directpost+JPEG preparation1image verified; bothorder/primary/adfallback/totalfailure/takeover server proof mockedAI/DB/messages PASS. No real client replay/reset or paid AI. Marketing ID still100/33; fixed supplied full-post path, not every inaccessible ad.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N13 | Deployed;842tests/Ruff/review/22hashes/newPID/publichealth/exactpost preparation/mockpipeline PASS | Incoming fullpost+question path fixed; ad-ID-only100/33 access remains unresolved; no live paid model/client replay |

## Micro N14 tasks

- [x] N14a: approved ANALYZE-only original account assignment, re-audit8exactads and prove actual source availability.
  Факт: owner completed Meta confirmation; selected only original Сандита and ANALYZE=1, campaign/creative/fullmanage=0; UI oneassetassigned and read-only listing verified. Isolated4-account access health PASS.8actualIDs still3accessible sources (2videos→10frames each,1image),5HTTP400/100/33. Actual source proofs pass for accessible3, not for5unknown. All4exact-DELETED Insights probes200/empty/no pagination. No AI/messages.
- [x] N14b: guarded fourth-account configuration if asset/source checks pass, private env backup/rollback, unchanged22source hashes, newPID/publichealth/all4 access/source evidence.
  Факт: conditional configuration gate not met for unresolved5sources; fourthasset grant supplied no additional source. Production allowlist/env deliberately unchanged; no unnecessary restart/config. LaterN15source-only rollout verifies22hashes/env/newPID/health. Do not claim four-account production allowlist.
- [x] N14c: document actual verified coverage, unresolved gaps and stable route, no unsupported universal promise.
  Факт: additional personal-account inspection initially auto-review denied; after exact owner permission UI reports setup needed before first campaign, so no extra asset/grant. Old5ownership remains unknown, deletion not proved. Follow-upN15 fixes independent provided-media route.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N14 | Reader4assetread verified,8audit3prepared/5Meta100/33;4deletedInsights empty; production env unchanged | Missing5ownership/source not inferred; N15provided-media route |

## Micro N15 tasks

- [x] N15a: red regressions for provided video/image/post priority despite ad_id, availability fallback, terminal guards, manager abort, truthful provenance/onevision/history.
  Факт:10initial red cases→green; additional invalid-ad identity red→guard→green, full3source fallback/first-post guard/allfailed singlemanager/voice+customer media coverage.17new tests, no weakened existing checks.
- [x] N15b: minimal supplied-source selection/preparation/provenance and safe presence diagnostics; targeted/full pytest/Ruff/read-only review.
  Факт:859fullpytest PASS/8existing warnings, Ruff/diff-check PASS, source/helper read-only review clear. First sandboxfullrun3native decoder failures, exact3pass with required nativefilesystem access then entire859samechecksPASS; no skipped/disabled checks. Supplied-source provenance and URLpresence-only logs implemented, identity/format/size guard preserved.
- [x] N15c: guarded source-only rollout if QA passes; env/credentials untouched,22hashes/newPID/publichealth, isolated success/failure/takeover proof and honest old5coverage.
  Факт:3-file preflight/apply/verify exit0, backupverified,22runtimehashes/env credentials launcher preserved, PID12560→6436 stable aroundhealth/newStartTime. Local/publichealthenabled/ready. FullpostN13/bothorders/failure/takeover mocksPASS; clicked/fallback/failure/guard/takeover mocksPASS. Actual canonical same-ad source decoder proof video10/photo1, not claimed observedwebhookURL. Old5APIIDs still100/33. No realclientreplay/reset/paidAI/messages. Reports n15-applied.json/n15-runtime-manifest.json.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N15 | Deployed;859tests/Ruff/review/22hashes/newPID/publichealth/source decoder/mocks PASS | Actual supplied-URL presence on next real ADS event remains to observe;5ad-ID-only sources unresolved |


## Micro N16 tasks (2026-10-12, до кода)

- [x] N16a: actual new-event/API/official-field investigation. Факт: Elbrus currentad200/C/VIDEO, actualvideo_url→invalid_media_url; otherphoto ad100/33. Official fullADSJSON says thumbnail. Boost lists200empty, authorized_adaccounts400, messageattachments200/noURL/referralfield400. No privateURL/token/clienttext dump.
- [x] N16b: red→green exact source priority/no thumbnail decoding/safe diagnostic and independent explicit catalog question regressions; minimal main/story/parser changes, preserve guards and takeover. Факт:29new meaningful cases; readonly review's Париж/ВДП/generic winter defects red→green fixed. Supplied-media tests updated without skips; identity/account/size/completeness/takeover guards retained.
- [x] N16c: fullpytest/Ruff/diff-check/read-onlyreview and server exact source + mocked failure/text/takeover proof; guarded deployment/rollback/22hashes/newPID/env/health evidence. Факт:888PASS/8existingwarnings/33.43s/Ruff/diff-checkPASS. Native filesystem access required, no exclusions. Guarded3file rollout/backup/env preservation/22manifest hashes verified; PID6436→5188/starttime21:19:41Z/local+publichealthok. Actual Elbrus ad120252561601750736 decoded10originalframes despite invalid preview; exact Dci_ZT0s-3b fullimage and mocked named/vague/takeover pipelinePASS. No paidAI/production messages/clientreplay/datachanges. Report n16-applied.json.
- [x] N16d: recover remaining five unavailable exact advertising sources or record specific proven external limitation; do not equate N16b/c with universal advertising reading. Факт:4exact Inbox/Viewad→latestreferral associations; C creative index exposes all4 IG IDs despite unavailable Ad nodes. Own IG GET exact permalink and full original preparation PASS:4images134822/586160/233574/601737bytes, noAI/messages. Proof n16-full-originals-proof.json. Older120252486000910736 cannot be inferred from newer120252331324000736/Viewad. PublicHTML previews/branded400/3/general opaqueID source lookup limitations recorded in runtime/instagram-business-context.md N16.
- [ ] N16e superseded by N17: owner rejects manual new-ad registration. Automatic source recovery only; recovered4associations remain evidence, not enabled fallback/universal coverage.

## N17 automatic source discovery

- [x] N17a: bounded investigation of actual failed Ad fields/type/status and documented automatic linkage candidates under existing permissions. Факт: five Ad/Boost node failures100/33; allstatus inventory589/4accounts/noid-adset-source matches; maximum Insights200 controls B/C present/targets absent; same company IG actor; shares five200empty; preview control200/failed331100/33; no standalone referral among220 logged target events. Reports n17-identity-probe.json/n17-insights-source.json/n17-preview-message-probe.json; no runtime changes. These negative results do not prove deletion or ownership.
- [x] N17b: investigate exact per-message Inbox source automation and record unavailable capability. Факт: two historical ad markers have zero links/interactive ancestor; global Viewad is latest331, cannot bind older910. C AdsManager exact331/maximum dates has no ads. Owner lacks company Instagram login; unrelated profile not used. Existing Facebook latest-source route is a candidate, not proved unattended/per-message automation.
- [ ] N17c deferred by owner's N18 policy: universal source-recovery implementation is no longer the active request. Concrete gap: global Viewad has no exact Ad ID or per-message binding. Read-only identity review rejects before/after latest MID/adID guard as sufficient proof because header can be stale. Permanent browser authentication is not configured. No manual registry, title/image guessing, new grants or browser session export/install made.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N16 | Two bugs deployed;7of8 observed originals proved readable;4recovered associations verified | Automatically binding the recovered sources is not implemented; manual registration rejected |
| N17 | Bounded API/UI investigation complete; no new exact universal route proved; runtime unchanged | Automatic latest-referral Business Suite candidate needs identity/authentication proof; arbitrary historical sources remain unresolved |

## Micro N18 tasks

- [x] N18a: meaningful red regressions for silent ADS outcomes/current context/phone/recent same-ad history/voice/standalone boundaries. Факт: initial18red→24green; review4rawcard bypasses red→green, transient session failure PASS; stable standalone receipt red→green.31newcases; superseded vague-ad/source tests updated, original decoder/guard assertions retained with a named customer question. No skips or real network.
- [x] N18b: minimal routing/silent-body/parser implementation, no nested processing lock; targeted green and read-only review. Факт: same-file lock-safe silent body, ADS before attachment branches, silent outer-error fallback, recent same-ad customer context and recognized voice gate.226compatibility casesPASS then32N18/parser casesPASS. Independent source review clear after two identified bypasses fixed. Full919pytestPASS/8existingwarnings/33.14s, Ruff/diff-checkPASS.
- [x] N18c: full QA/Ruff/diff-check, guarded source-only deployment/rollback/manifest/env/newPID/health/mock proof. Факт:919fullpytestPASS/8existingwarnings/33.14s/Ruff/diff-check, independent source review clear. Rollout review's manifest-path guard corrected; helper compile/Ruff and final preflightPASS. Backup verified, two sources applied,22runtimeSHA/env/ads-token/launcher preserved, PID5188→11348/start23:19:34Z/local+publichealthenabled/ready. Staged and installed seven mocked outcomes/standalone boundary+dedupPASS; verifyexit0. Apply stdout applied=true but SSHexit1 during restart; verified actual new process/hashes/state, no unsafe re-apply. No client replay/reset/paidAI or real manual external sends. Report:n18-applied.json.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N18 | Complete and deployed;919tests/Ruff/reviews/22hashes/newPID/local+publichealth/staged+installedmockproofPASS | Optional new real user test; existing takeover and notification limits apply |

## Quick N19 tasks

- [x] N19a: meaningful red regressions for screenshot questions/vague/novel subjects/standalone/unsupported ADS and one-model decision outcomes, invalid envelope/contact/voice/failure/limit/takeover. Факт: initial29red/1green→30green; source review found mixed typed+failed voice status and post-STT guard defects,2red→3green.33new casesPASS, no real model calls/client messages.
- [x] N19b: remove lexical gate/state, add bounded ADS response contract/parser and lock-safe silent result handling; targeted green and source review. Факт: lexical functions/state removed; one JSON decision+reply call; silent handoff before sends/phone acknowledgements.190compatibility casesPASS, final952fullpytestPASS/8existingwarnings/50.61s/Ruff/diff-checkPASS; independent source review clear after voice fixes.
- [x] N19c: full QA/Ruff/evidence, guarded two-file staged/installed mock proof and source-only deployment preserving private settings/client data; report live-model validation limits. Факт:952fullpytestPASS/8existingwarnings/50.61s/Ruff/diff-check/source+rollout reviewPASS. Rollout review found invalid visual mock, corrected to real StoryMedia shape; helper compile/Ruff/preflightPASS. Verified backup/twofiles/22SHA/env/ads-token/launcher preserved/PID11348→8456/start2026-10-14T11:21:16Z/local+publichealthok. Staged+installed13mockedscenarios/boundary+dedupPASS. Apply stdout applied=true with SSHexit1 at restart, independent verifyexit0 confirmed actual installed state, no re-apply. No live paidAI/clientreplay/reset/manual external messages. Report:n19-applied.json.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N19 | Complete and deployed;952tests/Ruff/reviews/22hashes/newPID/local+publichealth/staged+installedmockproofPASS | Real DeepSeek semantic quality can be observed on new normal incoming messages; mocks verify routing only |

## N20 read-only investigation

- [x] Verify actual screenshot source against installed resolver and original decoder. Факт: ad120255819105930322 HTTP200/exact DeI-3NiA_5L/VIDEO/10frames/649caption characters; no model call.
- [x] Check new official source candidates with bounded positive/negative controls. Факт: failed331 still100/33; exact activities oid returns0rows in four accounts over2026-07-14..2026-10-14, control returns3exact rows. Meta changelog confirms comments webhook explicit ad_id/original_media_id pair; partial coverage only.
- [ ] Prove universal automatic exact source retrieval. Still unresolved; no production change or inferred mapping. Факт: runtime/instagram-business-context.md N20, n20-source-check.json, n20-activities-check.json.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N20 research | Completed bounded verification; screenshot source works, universal retrieval unproved | Resolve failed Ad ID access/identity through Meta; comments indexing is only a partial candidate, not a guarantee |

## N21 permissions research

- [x] Audit official docs and current token/asset/app-level permissions. Факт: live Meta UI, debug_token/permissions/adaccounts200, two directAd positive controls200, failed331id-only100/33. No new grants.
- [x] Test newly discovered official IGMedia boost_ads_list on known original media. Факт: five media IDs/two token families; no recovered ad mapping, empty lists/explicit ad-copy rejection/source-token10033 recorded. Helpers RuffPASS, probes exit0; source docs and reports in runtime N21.
- [ ] Establish actual cause and restore inaccessible Ad IDs. No confirmed missing permission; combined read-only scopes are a possible controlled next experiment requiring explicit authorization.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N21 | Read-only permissions audit complete; no production change | Optional combined-scope read-only diagnostic test; never describe it as a verified fix |

## N22 authorized permission comparison

- [x] Issue diagnostic combined USER token and verify identity/actual grants. Факт: official Explorer USER Danila, requested read scopes granted alongside prior permissions. Shared-grant side effect restored; see runtime N22.
- [x] Compare failed Ad and original mappings against working controls. Факт: failed331100/33; working Ad readable; working organic explicit boost mapping returned; four problematic media return no mapping. This is not universal recovery.
- [x] Verify original production access after restoration. Факт: server PAGE valid/previous scopes restored plusads_read; SYSTEM_USER unchanged; page/IG/subscribed_apps200/messages retained/localhealth200ok/enabled+ready. No client send/replay or runtime deployment.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N22 | Authorized combined-token test complete; failed Ad unresolved; production access restored and verified | Evidence-based Meta support case if authorized; no basis for arbitrary ads_management expansion |

## Micro N24 tasks

- [x] N24a: confirm provider JSON+vision support and add meaningful red regressions for formatting, reasons, visual request format, observed queries and safe technical gist. Факт: primary DeepSeek JSON/Vision/ChatCompletions docs support the combination; no paid call. After fixture import correction,25red/1green expose current contract/factory/fallback failures.
- [x] N24b: implement opt-in visual JSON, bounded fence normalization/validation diagnostics and customer-question technical fallback; targeted green. Факт:59targetedPASS after catching/fixing text-provider fallback's missing media access. Extra metadata privacy regression added; no semantic guessing/second model call/server changes.
- [x] N24c: full pytest/Ruff/diff check, read-only review and synchronized evidence. Факт: independent60targetedPASS/review clear;979fullpytestPASS/8existing warnings/37.57s, Ruff/diff checkPASS. Initial full run976PASS/3native decode failures in sandbox; fresh-temp native rerun3PASS, full rerun979PASS outside sandbox (shared default pytest folder ACL failure corrected without code changes/skips). No server actions or paid model calls.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N24 | Deployed;979tests/Ruff/reviews/22hashes/env/credential preservation/newPID/local+publichealth/staged+installed18casesPASS | Real DeepSeek semantic quality remains unverified by mocks; new normal incoming messages can exercise it |

- [x] N24d: authorized guarded two-file rollout, staged+installed isolated proof, backup/22manifest/env/credential preservation and new-process/health verification. Факт: helper compile/Ruff/read-only rollout review/preflightPASS; two-source backup/22hashes/env/launcher/ads-token preserved. Apply stdoutapplied=true/SSHexit1 at restart; independent verifyexit0 confirmed newPID8456→17644/start2026-10-15T17:35:57Z/localhealthok/staged+installed18cases/boundary+dedupPASS. Public curl200ok after PowerShell timeout; no rollback/reapply needed. Local canonical manifest synchronized exactly2entries/20retained. Safe report:n24-applied.json.

## Micro N25 tasks

- [x] N25a: meaningful red regressions for empty-first recovery, final failure,
  manager takeover, cancellation, media identity, privacy and existing controls.
  Факт: 21red/4green before the fix; review's persisted takeover/provider-error
  edge reproduced separately (1red/1green). 31 focused cases now pass, including
  current phone, notification failure, oversize/type and both takeover statuses.
- [x] N25b: implement maximum one empty-string retry; targeted green, independent
  read-only source review; keep other rejection paths and notification semantics.
  Факт: 90 targetedPASS; second provider exception clears prior response metadata;
  common fresh-session guard closes the independently reproduced limit3 takeover
  issue. Read-only re-review clear. См. .kiro/decisions/0002-ad-empty-response-retry.md.
- [x] N25c: full pytest/Ruff/diff check and synchronized spec/runtime evidence.
  Факт: final1009fullpytestPASS/8pre-existing warnings/36.25s; Ruff/diff/micro-spec
  checkPASS. No server actions/live model probes; recovery feature remains paused.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N25 | Deployed with N26;23SHA/newPID/health and29installed mock cases PASS | Live provider recovery remains unverified by mocks |

## Micro N27 tasks

- [x] N27a: red regressions for malformed schema/JSON recovery, shared two-call
  bound, current-phone handoff, media identity, takeover/cancellation and safe logs.
  Факт: initial21RED/6GREEN;29new regressions nowPASS.
- [x] N27b: implement trusted format reminder and bounded recovery; targeted
  green and independent read-only review. Record the decision through CLI.
  Факт:146focusedPASS/review clear; см. .kiro/decisions/0004-ad-json-format-recovery.md.
- [x] N27c: full pytest/Ruff/diff checks, isolated real provider verification,
  synchronized evidence and concrete deployment/rollback preparation.
  Факт:1071fullPASS/8warnings/31.07s; Ruff/diff/micro-spec/helper proof/reviewsPASS.
  Three real corrective API calls valid after synthetic defects; server24SHA/backupPASS.
- [x] N27d: supersede the obsolete two-file rollout with N28 unified response.
  Факт: original production apply was rejected before execution; no workaround
  or deployment performed. N28 replaces that candidate with four source files.
- [x] N27e: owner "воспроизведи": run a bounded isolated full-handler trial with
  real unmodified provider responses, reconstructed historical requests and
  ordinary edge cases. Capture provider/application equality, actual validation
  reasons and recovery. No synthetic malformed replies, production writes,
  client/manager sends or deployment; report honestly if not reproduced.
  Original32-case/48HTTP trial rejected before execution by automatic approval
  review for scope/cost/data consent. Reduced to6synthetic text scenarios and
  max12paidHTTP, no real client histories/media. Explicit approval:
  "Да, до 12 вызовов DeepSeek". Free preflight:0HTTP/24runtimeSHA unchangedPASS.
  Факт:4completed scenarios/6realHTTP, stopped after natural invalid_fields.
  Provider returned decision/reply without context (stop,1198chars); actual
  full-handler retry returned all3stringfields and valid. Request ID
  0694c2f98c6a4c23b92cab47662293e6. Also388ASCIIspaces -> valid on actual retry.
  Wire/AIMessage SHA equality6/6; saved raw pair hashesPASS. Initial prompt AST
  equals production after excluding the unused retry helper.24runtimeSHA/PID15500/
  localhealth unchangedPASS;0real sends/notifications/session writes. Private
  diagnostic artifacts:json-natural-repro-20261016/{probe.py,captured-pair.json,
  verified-proof.json,evidence.md}. Historical provider bodies remain unavailable;
  do not infer their exact missing fields from this new reproduction.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N27 | Recovery verified and incorporated into N28; original two-file rollout superseded | Use N28 candidate; production unchanged |

## Micro N26 tasks

- [x] N26a: red tests for retained output/schema/whitespace, both attempts,
  ordinary/visual paths, safe metadata, redaction and all failure/leak boundaries.
  Факт:6red integration cases before implementation. Review's redaction issues
  reproduced in6extraRED cases, fixed;27new/117targetedPASS after correcting the
  ordinary image fixture to use enabled mocked prepare_images.
- [x] N26b: implement separate bounded journal and opt-out, integrate sole call
  site before gates, isolate test files and pass targeted/source privacy review.
  Факт: non-propagating handler with safe handleError and temporary test paths;
  short configured secrets/Basic/API-key/quoted values/Telegram URLs masked.
  Independent read-only re-review clear. См. .kiro/decisions/0003-deepseek-response-journal.md.
- [x] N26c: full pytest/Ruff/diff/micro-spec checks and synchronized evidence.
  Факт: final1036fullpytestPASS/8pre-existingwarnings/38.72s; Ruff/diff/micro-spec
  checkPASS, runtime/development notes synchronized. No deployment/live AI calls.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N26 | Deployed;27new/117targeted/1036full tests,23SHA/newPID/local+publichealth and29installed cases PASS | Journal records future returned responses; old outputs unavailable |

- [x] N26d: authorized N25+N26 guarded three-file rollout, backup/rollback,
  staged+installed mocks,23SHA/env/credential/launcher preservation, changed PID
  and local/publichealth verification; record restart transport uncertainty.
  Факт: rollback validation-before-write, atomic replacement, restart-unknown
  guards corrected/re-reviewed; isolated bad-backup/restore proofPASS. Server
  preflight cp1251 output failure fixed in helper;29staged+installedcases/dedupPASS.
  Backup/23SHA/env/launcher/ads credential preservation confirmed, PID17644->17148,
  start2026-10-15T20:52:43Z/local+publichealth200ok. Apply stdoutapplied=true/SSHexit1,
  independent verifyexit0; no reapply/rollback. No real replay/messages/paid trials.
  Production journal has no records yet after restart (lazy);no journal errors.
  Safe artifact:n26-applied.json; runtime/deepseek-response-journal.md.
## Quick N28 tasks

- [x] N28a: read existing paths/spec, define one schema and record decision by
  decisions CLI scan/add/review/approve. Requirements N28.1–N28.5.
  Факт: см. .kiro/decisions/0005-unified-model-json.md (CLI5/6 accepted).
- [x] N28b: meaningful red regressions for unified schema, all routes/three
  outcomes, no fresh markers, bounded recovery/final failure and current phone.
  Факт: first34cases32RED/2GREEN before code; inline phone4RED, latest tour4RED,
  contact-only phrase6RED, first-person1RED/1GREEN reproduced before their fixes.
  Explicit envelopes replace fixture's raw-text adapter; negative strings stay raw.
- [x] N28c: implement unified prompt/factories/validator/handler, explicitly
  migrate test envelopes, preserve all business/media/privacy checks; green.
  Факт:68new unified regressions;187phone/context/voice/engine targetedPASS;
  remove separate ADS factory/schema and fresh marker parser. Inline contact
  preserves latest tour/date/budget or prior topic for a contact-only phrase.
- [x] N28d: focused and full tests/Ruff/diff, independent read-only review, docs/
  spec/evidence synchronized. Paid live verification only with explicit scope.
  Факт:1136fullPASS/8pre-existingwarnings/62.57s; Ruff/diffPASS. Read-only review
  found and verified phone/context regressions, now covered; isolated harness review
  clear. Three real full-handler calls valid first try: VDP reply only, manager
  reply+notification, vague ADS silent notification.3/3wire hashes/actual schemas/
  captured outcomes asserted. Paid budget9of12used including previous6call trial.
  24productionSHA/4stagedSHA/PID15500/localhealth unchangedPASS;0real client/manager
  sends/session writes. No deployment. См. runtime/unified-model-json.md and
  .kiro/decisions/0005-unified-model-json.md.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N28 | Deployed;1136tests/3real staged cases,24SHA/newPID/local+publichealth/installed contractPASS | Ordinary production observation; inbound recovery remains paused |

- [x] N28e: owner explicitly requested «деплой». Verify exact four-file candidate,
  current24-file production baseline and existing launcher/credentials; back up,
  apply atomically, request the normal restart, verify new process/local+public
  health/all24SHA and installed contract without sending customer messages.
  Preserve sessions/settings and prior FAQ retirement; rollback must restore
  exact original four files+manifest if verification fails. No new paid calls.
  Факт: four-file candidate/24baselineSHA/5backupSHA verified; offline rollback
  proof and read-only reviewPASS. Apply/normal restart/24updatedSHA/protected
  config/FAQretirementPASS. PID15500 ->15716,start2026-10-16T15:42:44.4215596Z;
  localhealth200ok, publichealth200ok from client PC. Installed common validator,
  one prompt contract/text+vision request JSON verified with external HTTP denied.
  Server self-request to public host returnedCloudflare403; separate external
  client GET200 established public availability, no Cloudflare changes needed.
  Post-restart recent logs:0errors/1actual model record valid. Canonical manifest
  synchronized from observed installed24entries; no new paid/manual customer
  sends or session writes. Private deployment-proof.json saved outside Git.

# Quick N29 tasks — 2026-10-18

## Quick N32 — global tool rollout

- [x] N32a: scope config/gate/health + ADR; default/invalid/all routing tests.
  Факт: defaultallowlist/unknown rejected/all actual foreign-client handler+health
  verified. См. .kiro/decisions/0011-global-tool-transport.md.
- [x] N32b: extend guarded rollout and inverse rollback tests, full pytest/Ruff/
  diff/read-only review, exact baseline/package/backup.
  Факт:1379PASS/8existingwarnings,Ruff/diff/reviewPASS; all→canary inverse rollback
  сохраняет новыеSQLite rows/receipts. Backup code/env/manifest/SQLite exactSHA.
- [x] N32c: install all scope with normal restart; verify PID/health/28SHA and
  preserved env/recovery/receipts; installed offline scope/factory proof.
  Факт: newscopekeyall,3changed sources/5filepackage,RestartTravelBot;
  8668→7228/start2026-10-18T13:36:18.3387989Z,healthok/scopeall/28SHA/envPASS.
  Overrides absent; installed nonallowlisted clients gate/text+vision PASSwith0network.
  Recovery remains allowlist1; no DB restore/pause/reset/extra manualpaidcalls.
- [x] N32d: sync manifest, document outcome and live observation limits.
  Факт: manifest synced28,private deployment proof/runtime note;0newerror lines
  в просмотренных logs,postrestartmodelrecords0,новыйliveответнеутверждаем.

| Progress N32 | Сейчас | Дальше |
| --- | --- | --- |
| Global | Tool transport deployed для всех;1379PASS,healthall,installedscopePASS | Первые обычные клиентские запросы; ручные прогоны не запускались |

## Quick N30 tasks — единый tool transport

## Quick N31 — tool canary deployment

- [x] N31a: read-only installed baseline/launcher; canary settings+both lane
  prompt/factory/parser isolation, tests and ADR.
  Факт: independent numeric deny-by-default allowlist; mixed requests и frozen
  retry проверены. Installed exact legacy constants/factories preserved.
  См. .kiro/decisions/0010-tool-transport-canary.md.
- [x] N31b: targeted/full pytest/Ruff/diff/read-only review, package and offline
  backup/rollback proof with protected DB/receipts.
  Факт:1375PASS/8existingwarnings, Ruff/diff/reviewPASS;3inverse rollout tests,
  half-install и новые DB receipts после install.5file package exactSHA;
  локальные изменённые тесты не выкладывались; прочие applicationSHA совпали.
- [x] N31c: install for verified tester numeric ID only, normal restart,
  health/installed hashes/config/old lane proof; no synthetic paid sends.
  Факт: Meta verified @_shelter_0, backup code/env/manifest/SQLite;5files+1key,
  штатный RestartTravelBot;7688→8668/start2026-10-18T12:55:08.3954367Z;
  localhealthok/model_tools1,28SHA/env except newkey/protected unchanged.
  Installed offline proof12legacy prompt+retry/2factory exact,0network calls.
  Publichealth Cloudflare403 с PC: внешний health не подтверждён.
- [x] N31d: manifest/spec/runtime evidence; ask new tester message if live
  validation remains; existing pauses/limits not silently reset.
  Факт: owner sent new test;1model attempt valid/tool_calls at12:57:19UTC,
  job answered/done,1087chars→2IGparts,bothsent/receipt/attempt1,0newerrors.
  Pausefalse/escalation_count0 read-only; resets0. Manifest synced28entries;
  private deployment proof saved, runtime note updated. No extra manual paidcalls.

| Progress N31 | Сейчас | Дальше |
| --- | --- | --- |
| Canary | Deployed only verified tester;live toolcall/2parts/no duplicates PASS | Расширение на всех требует отдельного согласования |

- [x] N30a: ADR scan/add/review/approve; проверить SDK raw tool envelope и точки
  интеграции read-only; source spec до кода.
  Факт: SDK converter терял duplicate keys и неверно нормализовал arguments;
  подтверждено read-only исследованием. ADR review5/6 -> accepted.
  См. .kiro/decisions/0009-model-tool-transport.md.
- [x] N30b: новые red tests factory/payload/raw parser и common-handler contracts;
  реализовать единый strict tool transport, prompt, validator boundary, logs.
  Факт:17SDK tests red(factory JSON) -> green, raw message сохранён до parsing.
  Документированный max_tokens2048 закреплён wire-тестом red -> green; оба
  SDK retries0. Неверный тип arguments терминален, форматный retry до2 попыток.
- [x] N30c: regression handler text/vision/voice/ad/contact/cap, format retry,
  delivery/recovery receipts/unknown/manager cancel с network denied.
  Факт:12 realSDK+MockTransport full-handler/recovery testsPASS (29 вместе с SDK).
  Частичная отправка/restart:1generation, подтверждённая часть не повторяется,
  unknown не переотправляется. Текущий телефон/cap/silent/takeover проверены.
- [x] N30d: full pytest/Ruff/diff, независимое read-only review, docs/runtime
  evidence; production/deploy/API calls не выполнять.
  Факт:1359PASS/8existingwarnings, Ruff/diffPASS; независимое review без блокеров.
  Три native decoder failures внутри sandbox исчезают в полном native прогоне.
  Общий decisions check: замечание tour-sync requirements уже было до N30 и
  вне задачи; собственный design связан с ADR0009. Ни деплоя, ни API calls.
  Evidence: runtime/deepseek-tool-transport.md.

| Progress N30 | Сейчас | Дальше |
| --- | --- | --- |
| Integration | Локально реализовано;1359PASS,29SDK/handler proof,reviewPASS | Отдельный деплой;installed manifest не менялся |

- [x] N29e: подготовить и проверить изолированную матрицу десяти дополнительных
  tool запросов, включая actual photo/10 original video frames; read-only review.
  Факт: isolated matrix+private preflight, SHA original photo/10frames verified;
  read-only review completed.46 initial/47 final focusedPASS; full1329PASS with
  8existingwarnings outside sandbox. Inside sandbox3native decoder tests failed
  decode_failed; identical full command outside sandbox passed. Ruff/diffPASS.
- [x] N29f: выполнить до десяти разрешённых вызовов, проверить raw format и смысл,
  SHA/config/health до/после; зафиксировать ограничения без заявления о доставке.
  Факт: exactly10 started/completedHTTP200, raw arguments10/10valid, no whitespace;
  reviewed semantics9/10 (limit warning omission). Wrong VDP predicate initially
  produced8/10; raw report preserved, separate reviewed proof explains correction.
  184198input/3104output tokens;1.64–3.28s.28SHA/env/health unchanged,0sends.
  Photo220€ and10frame route recognized; no full-handler/receipt guarantees.

- [x] N29a: verify official tool_choice/strict schema, prepare isolated six-call
  harness and read-only production baseline without changing live behavior.
  Факт: official named tool requires thinking.disabled; strict endpoint/schema
  verified, nullable compatibility left experimental. Current28SHA/healthPASS.
- [x] N29b: offline malformed/missing/multiple/duplicate/type/length/silent tests;
  preflight denied external HTTP, existing parser retained; read-only review.
  Факт:34offline casesPASS,1317fullPASS/8existingwarnings, Ruff/diffPASS;
  serverpreflight network-denied:0externalcalls,6planned,28runtimeSHA verified.
  Read-only review found diagnostic envelope bug; malformed200/strict400/fallback
  and callreservation regressions reproduced red -> green before paid execution.
- [x] N29c: only after explicit new paid budget, run bounded actual tool probes;
  private raw responses + safe summary, original SHA/config/health preserved.
  Факт: owner explicitly approved up to6; exactly6 completed. JSONcontrol388
  spaces/empty_response; ordinarytool2/2 and strictproblem/manager/silent3/3 valid
  and semantic_ok, exactlyone prepare_response each. Nullable strict schema works.
  110482prompt/2249completion tokens;28runtimeSHA/env/health preserved,0sends.
- [x] N29d: document success/failure and limitations; no production migration
  or deployment inferred. Architecture acceptance requires separate verified change.
  Факт: private plan/rawresponses/safeproof archived; runtime evidence updated.
  Text-only directAPI spike, not integrated handler/media/history migration or
  production-ready guarantee. Remaining paid budget0; no further calls.

| Progress | Сейчас | Дальше |
| --- | --- | --- |
| N29 spike+extension | Original6calls+10new: new tool10/10 format,9/10 semantics,photo/video PASS; production unchanged | Full tool transport integration/handler proof requires next scoped change; no paid calls remain |
