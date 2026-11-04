# GigaAM incoming voice integration — 2026-10-10

Implemented and explicitly authorized deployment completed; production flag is on, owner live check pending.

| Before | After | Evidence |
| --- | --- | --- |
| Audio attachment becomes unsupported/non-text | Flagged voice parser retains ordered audio/text/visual parts and every MID | tests/test_voice_messages.py |
| No local speech pipeline | Isolated resident GigaAM worker; bounded queue/download/duration; cancellable owned process | tests/test_voice_media.py, real server worker/client proofs |
| Recognition error would ask to retry only | Immediate short manager notification without DeepSeek, followed by retry/text request | Failure/takeover/send-failure regressions |
| Model might supply an old phone | Voice handoff accepts only an explicit, unambiguous current phone; model-only phone suppressed | Three contact-source regressions |

Runtime: existing pinned GigaAM-v3-e2e-rnnt FP32 export, onnx-asr0.12.0,
ONNX Runtime1.23.2/numpy2.2.6/PyAV16.1.0, isolated environment. Added only PyAV
to the retained GigaAM environment; production packages and alternative STT engines
unchanged. Model SHA checked at worker startup, no model download or network STT.
CPU2intra/1inter/no-spin; one worker, admission8/acquire30s/job90s. Up to3voices,
10MiB each/20MiB total/180s decoded total. Local WAV/MP4/OGG/MP3/FLAC decoding,
audio-only stream, mono16kfloat32. Pause-biased chunks≤25s overlap0.5s; conservative
boundary word deduplication. Recognized input retains the existing1000-character
guard; exceeding it hands off, without cutting speech or calling DeepSeek.

Actual application client was run using the production Python with staged source,
saved own original M4A and native Instagram audio-only MP4/AAC48kstereo. Network
download replaced only with a copy of these saved inputs; real decoding/model/
private pipe/cancellation/temp cleanup ran. Two originals in one request passed;
resident reuse passed; silence produced voice_empty, old worker stopped and next
request started a new worker; explicit close and temp cleanup passed. No DeepSeek,
Instagram or manager messages sent. Native worker also processed43.127s joined own
recording and45.39s synthetic control, retaining complete duration. Native warm
wall times21.439s→2.108s,6.912s→0.525s,43.127s→5.128s; startup2.789s. These are
sample measurements, not latency/accuracy guarantees. CPU counters from this new
harness were uninformative (zero), so no new CPU claim is based on them; earlier
trial CPU/RAM report remains the measured reference. Long natural/noisy/contact
accuracy is still not measured. WindowsServer2019 ORT support warning persists.

QA: full local pytest709PASS; Ruff and diff check PASS.55 focused voice tests,
including spawn-cancellation ownership, no credentials on downloads, redirect/
length/type/encoding limits, long chunk coverage, guard/takeover/phone/short handoff.
Read-only final review: six initial issues addressed, no remaining must-fix findings.
Preflight verifies all17 deployed baseline hashes, staged11-file manifest, native
proofs, local/public health and unchanged listener2984. Helper-only paths used;
working app source/config/launcher/data/sessions were untouched during staging;
the subsequently authorized deployment is recorded below.

Private evidence is outside Git: native-proof.json/client-proof.json/preflight.json
and voice-integration-bundle manifest. Prepared eight-file apply artifact backs up
source and server .env, checks old/new hashes, changes only three voice settings,
restores existing source/env if copy fails. Execution and scheduled bot restart
required deployment authorization. Authorized sequence: refresh preflight; backup/
apply; existing RestartTravelBot task; verify new listener, health, flags/paths and
worker ownership; real owner voice. Rollback restores exact backup source/env and
restarts via the same task, removing only checksum-confirmed newly introduced
files under the application root. No database/takeover/limits reset.

Initial QA mock declared gzip over plain bytes and failed before downloader code;
changed to streaming response, same encoding-rejection case passed. Remote PS5
JSON-array binding caused a preflight path-array error; corrected input binding,
same17-source/stage/health/proof checks passed. Earlier SSH command quoting issue
was corrected with a short encoded script; no production mutation occurred.

Deployment: owner explicitly answered «Да, выложить и включить». Eight named
runtime files applied, only three VOICE_* settings enabled in server .env. Backup
and rollback hashes strengthened after artifact review, before any mutation.
Backup/apply checks passed, scheduled RestartTravelBot performed, listener2984→7116
(parent13604). Actual deployed client loaded enabled settings and recognized both
saved originals; silence produced voice_empty, owned worker6804 stopped, temporary
audio removed. Applied source/env9SHA, unrelated deployed source and original
launcher SHA verified; local/public health both ok. Production Python packages,
DB/takeover/limits were not changed by deployment; no manual paid/client/manager
calls. Default flag staysfalse for other installations. Private production-smoke/
verification/applied manifests retained outsideGit; owner live voice was pending
at initial deployment and passed in the subsequent live check below.
First production smoke's Python urllib public GET returned403; native/local smoke
was repeated separately, and public health remained independently required and
passed through the normal PowerShell verifier. No firewall/auth changes made.

Live completion:2026-10-10 14:16UTC fresh Instagram voice about a Serbia tour
recognized, saved with voice marker and answered14:16:40Z, no manager service block
or new takeover. Earlier test was blocked by an own echo arriving before API send
returned; reproduced and fixed per pre-code bugfix.md with5regressions and714 full
tests/Ruff/review PASS. Single-file guarded patch/20source SHA/env/launcher/local
and public health verified, listener14396. Owner-authorized admin pause reset
changed only manager_last_at; history/escalation_count3 preserved. Telegram handoff
not asserted by this live test. See runtime/instagram-early-echo-takeover.md.
