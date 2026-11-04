# Isolated local voice trial

Date:2026-10-10. Owner chose local Whisper, first speed/quality before integration.
Existing audio parser discards URL; no live voice understanding was enabled.

Runtime is isolated in deployment helper directory: faster-whisper1.2.1,
CTranslate2 4.8.2, PyAV16.1.0 (compatibility pin), CPU/INT8/2threads/1worker/beam5/Russian/VAD,
official Systran small multilingual model, separate cache. No system FFmpeg/GPU
installation, no changes to production Python environment/config/data/code.

Setup/pip check/syntax checks passed. First model download+load46.186s;
cached load2.489s, peak working set706.2MiB. Three-second silence:0segments,
0characters,0.066s. Silence is setup proof, NOT speech latency/accuracy.
17 deployed source hashes remained equal; public health ok, no restart,
paid inference, real client reply or manager notification.

Actual owner M4A21.439s/357928bytes: initial PyAV19.0.1 decode raised TypeError
for metadata_errors. Silence smoke bypassed decoder, so could not detect it.
Pin16.1.0, pip check and exact same M4A rerun PASS. Small load2.426s,
STT6.584s, process peak706.3MiB; raw phrase «Пух Варшаву» needs accuracy review.
Owner confirms this sample concerns visiting mother separately from tour program;
the earlier pasted visa text is a different sample, not a literal reference.
Dates/phone not tested on this sample (none present); no literal reference/WER.
Same owner sample, identical settings/no reference prompts: small new pair
5.497/6.146s/706.6MiB, medium17.240/16.273s/1767.1MiB,
turbo17.268/18.282s/1908.0MiB. Each model's two repetitions yield equal raw text.
Small garbles initial tour phrase; medium omits noun; turbo preserves «тур в
Варшаву» plus mother/program question. Owner confirmed this actual file's topic.
Turbo is recommended integration candidate, not generally verified perfect STT.
Small/turbo recorded input SHA matches local owner file; private per-model results
and transcripts retained outside Git. Decode small0.060s/turbo0.044s.
Turbo first load145.566s includes model download; later cached load5.615s,
silence3s →0segments/0chars/0.065s. Models remain isolated, no paid AI calls.
An attempt at public Google FLEURS ru_ru rows returned
external HTTP500; this is dataset unavailability, not evidence of STT failure.
Do not invent a quality result. Model load timing includes native initialization;
production integration should reuse a loaded model with bounded concurrency.
STT timing excludes file decode and model load; process peak is not incremental
model memory. Updated helper syntax PASS,17 remote source SHA/health unchanged.

Sources: https://github.com/SYSTRAN/faster-whisper
https://pypi.org/project/faster-whisper/
https://huggingface.co/Systran/faster-whisper-small
https://huggingface.co/Systran/faster-whisper-medium
https://raw.githubusercontent.com/SYSTRAN/faster-whisper/v1.2.1/faster_whisper/utils.py
https://huggingface.co/openai/whisper-large-v3-turbo
https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo
https://pypi.org/project/av/16.1.0/

Integration follow-up: preserve audio URL/MID, voice-aware ordered5-second batch,
transcript+text+visual single DeepSeek call, recheck guard/takeover after STT,
proper audio MIME/container/download bounds and temporary cleanup. Video audio
remains excluded. Keep manager gist concise, contact provenance explicit.

Owner CPU-load follow-up: turbo same M4A21.439s twice, process CPU time
42.797s/33.000s across elapsed21.435s/16.509s,16 logical CPUs →12.48%/12.49%
average share of total logical CPU capacity during STT (approximately2 fully
busy logical CPUs). Measurement includes native CTranslate2 threads/VAD and
fully consumed lazy segments; excludes model load/decode. Not system-wide CPU
and not instantaneous peak. Peak working set1891.8MiB, ~11.7% of15.77GiB RAM.
Cached model load4.614s, decode0.045s, input SHA and transcription unchanged.
Syntax + read-only formula review PASS; separate CPU report retained privately.
Proposed integration: shared loaded model and one STT job at a time; concurrency
has not been benchmarked. No production code/config/data changes.
# Native Instagram download proof (2026-10-10)

The owner sent a native Instagram voice. Existing parser logs audio type but
discards payload.url. Read-only Graph lookup returned200/id+from without
attachments; its attachment edge returned200/empty. This cannot establish that
incoming audio is undownloadable. LocalProtocolError during the first helper
attempt was fixed by setting production CWD before loading config; rerun200.

Owner separately authorized two production restarts for isolated own-account
capture+restore. Temporary ASGI wrapper delegated the existing parser unchanged,
captured once after signature validation, validated HTTPS CDN redirects, bounded
download10MiB/45s, and excluded URL/token from reports.12 focused checks PASS;
PowerShell5 wrapped JSON array counted incorrectly FAIL→unwrapped/check PASS.

New actual webhook payload.url downloadedHTTP200:36384bytes, MIME video/mp4,
MP4/isom signature, one audio stream AAC48000Hz/stereo,6.912seconds,40409bit/s.
PyAV16.1.0 in isolated Whisper environment fully decoded162frames/6.912seconds.
SHA256:a62338c52900affc3c9b3146812362f948ef2354d4f780a35f9b5bd9a26287e6.
Private metadata reports and audio retained outside application/Git; no STT or
external recognition provider used. MIME video/mp4 does not imply a video track.
This is one observed native recording, not a guarantee for every Instagram app.

Original launcher restored byte-for-byte;17 application source hashes unchanged;
normal listener process renewed and local/public health both ok. Voice recognition
integration remains pending. Download must happen from incoming webhook rather
than relying on message-history API to recover the media URL later.

# Matched Parakeet comparison (2026-10-10)

Owner authorized isolated local Parakeet v3 Q8 trial and comparison with Whisper.
Official NeMo-Speech.cpp0.2.0 portable Windows CPU runtime and714MB weights SHA
verified; own21.439s M4A/native6.912s AAC and3s silence converted to identicalPCM.
Four engines, first+two warm passes perfile:36runs, verifier/read-only review PASS.
Parakeet warm6.337/2.664s vs turbo20.933/19.946s (3.303x/7.486x speedups).
Small6.060/4.198s, medium16.563/12.382s. PeakRAM856.19 vs turbo1878.79MiB;
after-main working-set snapshots847.67 vs981.205MiB, only13.61% reduction vs
54.43% peak reduction. Speech CPU about12.5%16logicalcapacity for all; shorter
Parakeet duration reduces main CPU-seconds by70.26% vs turbo.
Parakeet preserves tour/mother/separate-program intent but omits «с»; turbo keeps
that phrase. Native Italy question recognized byall; allrepeattexts stable and
silence empty. No literal reference/WER/contacts/dates/noise/concurrency claim.
This trial supersedes earlier Whisper-only turbo recommendation with Parakeet
as candidate, not a production decision. See [full comparison](parakeet-whisper-comparison.md)
for raw input/model SHA, settings, scope differences, limitations and sources.
Production17SHA/launcher/listener2984 unchanged; local/publichealthok;
trial native process exited, no restart/client/manager/externalSTT calls.

# GigaAM comparison (2026-10-10)

Owner «делай» authorized isolatedGigaAM-v3-e2e-rnnt trial, notprodrollout.
Community ONNX FP32 export pinnedrevision/SHAverified, separateonnx-asr0.12.0/
ORT1.23.2/numpy2.2.6, noTorch/no productiondeps.42newpasses, plus36priorrecords,
verifier78PASS. Defaultwarm1.789/.357s withCPU~16/25%, no-spin2.721/.854s with
CPU~12.4%; no-spin reducesintensity butCPU-seconds18..38%higher than default.
Bothsettings same text, ownWarsawquestion phrasing retained morefaithfully;
syntheticIrina45.39s phone/date/price/tours preserved. Joinedown43.127s and
syntheticcontrol sharedlosslessPCMchunks≤25s; no arbitrarylong/noise/contacts
humanaccuracyclaim. Parakeet synthetic«Познань»→«Поздном», turbo fieldsright.
AftermainGigaAM1021.9MiB vsParakeet847.67; separateOSwarningServer2019 despite
successfulrun. GigaAM candidate supersedesParakeet trialrecommendation, not
productiondecision. See [full GigaAM comparison](gigaam-whisper-parakeet-comparison.md).
Final17productionSHA/launcher/listener2984 unchanged/local+publichealthok;
onlynormalPython2984/14312remain, alltrialprocessesexit. V1d voiceintegrationpending.
