# Incoming story mention and direct video

Date: 2026-10-09. M2 supersedes M1 image-only mention and A2 direct-video fallback.

## Symptom / cause

Story mention was routed through strict IMAGE-only preparation. Full MP4 source
therefore failed before vision. Direct video also used unknown non-text fallback.
Input types mapped one-to-one with photographs; video expands to ten output
images and needs separate output types to avoid shifting mention markers.

## Fix

Reuse existing VIDEO preparation/decoder/timing. Only story_mention auto-detects
JPEG/PNG/MP4 by bytes; ordinary image remains IMAGE, direct video stays VIDEO.
Each source has a separate folder and input index in frame labels. Optional
StoryMedia.image_types maps output frames, media_types maps input files;
prompt uses output provenance, history uses source indices and resolved formats.
Native VIDEO produces ten chronological frames, no audio. Whole input validation,
Meta CDN allowlist/no token/no redirects, bytes/duration/pixels/aggregate limits,
timeout/concurrency/cleanup unchanged. All GIF bytes are skipped; explicit
GIF/sticker reserves MID without collector/AI/reply/manager, including replies.
File/product with any caption/story context uses deterministic manager path.

## Verification / limits

Initial12 synthetic service failures → PASS. Full local601 PASS/Ruff PASS;
42 additional cases preserve prior checks while updating changed contracts.
Native local real MP4 → two separate video sources/20 total frames, source1
0.000–8.500s, expanded source types verified. No paid AI or external media API calls; download supplied from existing local test file.
Read-only review fixes for inline GIF ignore and file/story precedence tested.
Server isolated stage599 PASS/2 previous JPEG-artifact skips/Ruff PASS.
Backup-visual, 8 files/17 SHA verified, listener3460 → 10076, local/public health
ok; real mention/direct delivery still awaits
user-generated test. Meta sticker-specific payload schema search had no results;
explicit known types and GIF magic supported, opaque unsupported is not guessed.
Expired/inaccessible URL, incomplete/unsupported video yields honest fallback.
Voice transcription remains deferred. No production data/config/limit mutations.
