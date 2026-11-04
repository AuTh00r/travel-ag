---
status: deployed-and-verified
date: 2026-10-20
scope: placement ad creative media; code-only production rollout
promoted_to: null
---

# Placement creative rejected despite readable ad

## Symptom and cause

Four owner-supplied active ads expose asset_feed_spec with optimization_type
PLACEMENT, two video and two image creatives. The resolver rejected every
nonempty feed. That terminal error also prevented the existing clicked-image
availability fallback. The configured account and ads_read access were valid.

A real isolated candidate check revealed a second independent failure: direct
creative GET returns HTTP200 without instagram_permalink_url for these four,
whereas creative expansion on the exact ad returns the verified permalink.
The first candidate still rejected all four; this failed proof was preserved.

## Fix and boundaries

Request creative fields expanded on the exact ad. Keep the legacy direct lookup
only for an ID-only reference; never merge partial creative snapshots. Preserve
ad/account/creative IDs, Instagram media ID/permalink and allowed CDN validation.
Accept PLACEMENT with marketing_variant provenance. Other nonempty or malformed
feeds remain unavailable but can fall through to an actual clicked image.

Canonical IG material proves association with this ad, not the variant seen by
the client. Preserve this limitation in prompt/history. Append the actual clicked
photo when available, separately labelled, with an explicit warning not to copy
conflicting prices/dates/conditions from canonical material onto the clicked
image. No arbitrary first asset, placement rule guessing, reverse ID mapping,
thumbnail-as-full-video, new permissions or extra model calls.

Keep the existing shared decoder, ten original frames/no audio for each video,
combined 100-frame/24MiB bounds, delivery rules and manager takeover. No-feed ads
retain their exact-source path. Conservative aggregate provenance prevents a
later exact source from erasing an earlier variant or clicked-only limitation.

## Verification

Initial regressions: 16 failed / 4 passed reproduce blanket rejection. An initial
pytest run could not access the system pytest temp directory; using a fresh local
basetemp allowed the actual tests to run without changing permissions or tests.
Three additional expanded-creative regressions reproduced the real permalink
failure, then passed. Final focused resolver/placement suite: 60 passed, including
29 new placement cases. New cases cover original IMAGE/VIDEO, malformed feeds,
exact IDs/permalinks/URLs, unknown-feed photo fallback, original plus clicked
media, optional photo failure, combined bytes/frame limits, manager takeover,
one mocked vision request, original detail, history and mixed provenance.

Final read-only candidate ran in a separate server Python process with in-memory
candidate code and actual authorized Graph GETs: all four supplied ads resolved
VIDEO, VIDEO, IMAGE, IMAGE, all marketing_variant, with original validated URLs.
Server source and configuration hashes were identical before/after. No media
download, model invocation, client/manager message, database write, config change,
restart or deployment was performed by this probe. Proof contains only safe
IDs/types/provenance/booleans and candidate SHA, no credentials or signed URLs.

Final full suite:1562 passed,8 preexisting warnings,63.84s. Ruff,
diff and micro-spec validation pass; independent read-only review found no blocker.
The existing ADR scan has three unrelated documentation warnings in meta-diagnostics
and tour-sync; this change has an accepted record and does not alter those specs.

## References and limitations

- .kiro/specs/media-understanding/requirements.md (N34)
- .kiro/decisions/0014-placement-ad-provenance.md
- https://developers.facebook.com/docs/marketing-api/dynamic-creative/placement-asset-customization/
- Safe probe artifacts: placement-instagram-media-probe.json,
  placement-candidate-readonly-proof.json (failed first candidate),
  placement-candidate-readonly-proof-final.json (successful candidate).

The two inaccessible referral ad IDs returning 100/33 are not mapped to the four
readable ads by this fix. Exact clicked video remains unproved when Meta supplies
no placement selector.

## Deployment

Separate owner authorization «деплой». Server isolated candidate tests60PASS;
exact controller rollback proof PASS for inverse/partial install, unexpected edit
refusal and preserving new receipts/unknown. Replaced three source files plus
manifest, no env/credentials/launchers/config/scope changes. PID5380→11436,
2026-10-20 17:06:34Z/20:06:34 Minsk. All31 installed entries and local/publichealth
verified. Recovery remains allowlist1; first-enable baselines preserved.

All296 previously confirmed receipts retained; cancelled/failed jobs preserved,
session revisions did not regress, active/pending/unknown0. Installed resolver
read all four actual ads as VIDEO/VIDEO/IMAGE/IMAGE, marketing_variant, original
media URLs validated. No post-restart warnings/errors in the first54s checked.
No manual messages or paid model calls. New customer flow remains to be observed.
Code-only rollback and source/manifest/online DB backup are retained in the
placement-ad-20261020 release bundle. Never restore that DB backup as code rollback.
