---
status: verified
date: 2026-10-11
scope: Instagram webhook, FastAPI, Windows Server 2019
evidence: .kiro/specs/media-understanding/tasks.md N8; tests/test_inbound_business_context.py; tests/test_network_isolation.py; private n8-applied.json
promoted_to: docs/ARCHITECTURE.md; docs/DEVELOPMENT.md
---

# Упоминания, рекламный контекст и деловые обращения

Symptom: бот отвечает на служебные mentions/coauthor cards, теряет источник
рекламного вопроса и отказывает предложению сотрудничества как посторонней теме.

Investigation: три независимых read-only проверки по просьбе владельца. Mention
имеет exact attachment type. Проверенное приглашение соавтора пришло как
unsupported_type; Graph exact MID вернул from/id и пустые attachments. Владелец
отверг silent обработку всех unsupported_type. Referral рекламы содержит title
«Рилс ВДП Рождество»; exact provided permalink resolver вернул post_unavailable,
Marketing GET exact ad — HTTP400/code100. Это не доказательство удаления поста.
Первичные источники:
https://developers.facebook.com/documentation/business-messaging/instagram-messaging/webhooks
https://github.com/facebook/facebook-python-business-sdk/blob/25.0.0/facebook_business/adobjects/adcreative.py

Root cause: mentions использовали прежний vision-путь; referral терялся при
замене/объединении событий и не передавался в AI. Security prompt запрещал все
нетуристические темы; media instruction требовала определить тур даже при
явном предложении сотрудничества.

Fix: exact mention целиком становится silent event до reaction/voice/media;
5s collector сохраняет самостоятельные соседние сообщения. Handler сохраняет
locks/takeover/лимит3, кратко уведомляет менеджера, не вызывает AI/decoder/client
send/queue при любом исходе. Referral сохраняет bounded title/private sources
отдельно от вопроса; ad_id не заменяет media ID. Доступные источники используют
существующий decoder и отдельные labels; история хранит только title/provenance.
Сотрудничество допускается как обращение к компании: короткая благодарность и
один вопрос при отсутствии деталей. Receipt по-прежнему формирует программа.

Verification: initial24 cases16FAIL→24PASS; review3FAIL→34PASS; targeted333PASS.
Полный suite выявил instance mock shadowing в двух новых tests; fixture получила
отдельный InstagramChannel, предшествующие163PASS, final791PASS/8existingwarnings.
Ruff/diff-check PASS; три повторных read-only reviews без существенных дефектов.
Guarded rollout изменил main/prompts/instagram, source/manifest backup проверен,
21SHA/env/launcher сохранены, listener2416→11352/local+publichealthok. Deployed
mocked proof: silent success/error/limit/takeover, raw reaction precedence,
unsupported unchanged, voice referral, adtitle prompt/history, cooperation media
intent и прежние4handoff outcomes/2API receipts/partial. В proof нет реальных
HTTP вызовов, сообщений или production DB writes.

Manifest sync: remote artifact прочитан отдельно; delta только3runtime entries,
локальная копия до правки проверена, canonical JSON совпадает с сервером.
Test entries отражают серверную старую копию, не текущие локальные regressions;
тестовые файлы на сервер не выкладывались. Нельзя проверять такой manifest как
снимок всей локальной рабочей копии: изменённые tests имеют другие SHA.

Test isolation incident: первый полный pytest старых batch tests не подменял
новый silent handler и отправил реальные Telegram карточки BATCH_CLIENT;
владелец уведомлён. Fixture теперь подменяет handler, autouse conftest запрещает
реальные sync/async httpx transports, оставляя MockTransport/ASGITransport.
Три guard regressions PASS. SQLite изоляция сама по себе не предотвращает
внешнюю отправку. Тестовые карточки не удалялись.

Portability limits: coauthor discriminator pending, общий unsupported_type не
изменён. Title-only контекст не равен полному видео; supplied URLs/post identity
проверены синтетически, их наличие в реальном webhook не обещается. Поздний
referral без сообщения не инициирует ответ. Prompt/mocked replies не гарантируют
живую формулировку. Лимит3/reset720hours и история/паузы не сбрасывались; live owner
проверка после rollout ещё не выполнена. Docs/decisions validation CLI отсутствует,
его проверка не выдаётся за пройденную.

Owner clarification (N9, 2026-10-11): третий screenshot относился к неуместному
«туров. с радостью подскажу.» и строчной букве, не к бизнес-политике. N8 cooperation
exception был ошибкой интерпретации root. N9 восстанавливает N7 BASE (кроме нового
общего style rule), SECURITY/ESCALATION/ACTION constants и исходную media instruction.
Transforms сохраняют исходную фразу, сами не меняют регистр. General prompt rule
требует заглавную букву/связную формулировку без пустого хвоста. Проверка equality
с SHA-verified N7 backup и plain/media/count0/count3 variants PASS; не использовать
regex для автоматической правки произвольных ссылок, брендов или текста клиента.
Позднее уточнение отменяет описание cooperation exception выше; оно остаётся
историей ошибочной первой выкладки.

N9 verification:5red→75targetedPASS/794fullPASS/8existingwarnings/Ruff/diff-check/
read-only review. Только prompt runtime file выложен с backup,21server SHA/env/
launcher/local+publichealth verified, listener11352→8928. Actual deployed policy
equality и прежние маршруты/receipts проверены под HTTP/AI/send/DB mocks, real calls0.
Canonical manifest sync delta1 с проверенной локальной копией; test entries
сохраняют серверные значения. Нового live wording proof нет.

N10 ad discovery (2026-10-11): previous generic100 failure now qualified by
debug_token metadata: valid typePAGE, exactconfiguredapp/page, granted scopes
business_management/instagram_basic/instagram_manage_messages/pages_manage_metadata/
pages_messaging/pages_read_engagement/pages_show_list/public_profile; no ads_read/
ads_management. Exact ad GET still100/subcode33. This proves a current access
blocker, not deletion/nonexistence of that ad. PAGE me/permissions and me/adaccounts
fail nonexistent field: wrong node for these edges, not evidence user has no ads.
Bounded extended published lookup exhausted8pages/767items, oldest2015-10-04,
supplied shortcode absent. Private safe artifact reports saved; no runtime/settings/
auth/source/data changes, no messages/AI/downloads.

Official route supported by Meta Marketing reference/SDK25: ad_id→ad creative
and account_id→video_id (including object_story_spec.video_data)→video.source;
images by exact image_hash→adaccount/adimages hashes filter; promoted IG source by
exact effective_instagram_media_id. Separate Facebook User/SystemUser token with
ads_read and adaccount asset access is recommended; messagingPAGE is not replaced.
Original of this ad not yet retrieved, requires authorized new access then actual
GET/decode validation. Dynamic asset_feed_spec/currently edited creative cannot
be claimed as exact historical impression; fallback registryad_id→verifiedoriginal
is an alternative when automatic advertising access is unavailable.
Sources:
https://developers.facebook.com/docs/marketing-api/get-started/authentication/
https://developers.facebook.com/docs/graph-api/reference/debug_token/
https://github.com/facebook/facebook-python-business-sdk/blob/25.0.0/facebook_business/adobjects/adcreative.py
https://github.com/facebook/facebook-python-business-sdk/blob/25.0.0/facebook_business/adobjects/advideo.py

N10 authorized UI setup,2026-10-11: owner confirmed Facebook saved profile.
Existing personal Marketing generator warns it revokes prior permissions; not used.
Created separate Employee Sundita Reader61595313984712. Exact ad ID filter in
Ads Manager proves Рилс ВДП Рождество is in Сандита Б2748504208879634.
Assigned only account ANALYZE (Смотреть результативность) and exact app TEST
(Тестирование приложения), both verified after refresh. ads_read Standard was
already active. Before TEST the System User wizard listed two advanced scopes;
after TEST ads_read appeared. This is empirical UI evidence, not a general promise.
Selected only ads_read with60-day expiry; owner completed emailed verification.
Token issued and /me/permissions confirms ads_read+public_profile only. No messaging
credential change or campaign/bot runtime edits. DEVELOP/MANAGE/full business
control were not granted. Matching Gmail profile and relevant Meta mail arrival
checked; one-time authentication code withheld/not retrieved or logged.
Sources: https://developers.facebook.com/docs/development/build-and-test/app-roles
https://developers.facebook.com/docs/graph-api/overview/access-levels

N10 exact video proof,2026-10-11: Graph Explorer v26.0 ads_read token reads exact
ad120255819105930322/account2748504208879634/creative1392757435898637. Creative
instagram_permalink_url matches DeI-3NiA_5L and returns source18125669482848686,
effective17947642536299061,FBvideo2200548047539257. FB video.source denied code10.
Existing PAGE token at production v25.0 successfully reads both exact IG IDs;
source has another permalink, rejected without downloading. Effective permalink
matches supplied ad exactly: VIDEO/media_url/caption617chars. Bounded CDN download
without token yields full valid MP46595346bytes/26.966667s, SHA
8ef2cd41282428a6adb8074f18fe743fe91eda5ed4339afa696c73c5fa884b87.
Native decoder generated10original JPEG frames0–26.933333s, no audio extracted.
Inspected frame shows Варшава–Дрезден–Прага/9–13декабря/260€; image720x1280.
Report exact-ad-ig-source-20261011.json and local exact-ad-20261011/source.mp4.
Initial diagnostic falsely treated manifest dict as frame list; next rerun hit
CreateNew on already generated frames. Helper corrected to validate existing
manifest/files; final same probe exit0, source bytes equal new download, frames
count/names/JPEG/hash verified. Frame provenance comes from first generation in
its initially empty exact-media folder, not an independent cache-origin sidecar.
Read-only review clear with this evidence limit. Env/launcher/21runtime SHA and
local health verified unchanged/ok. New ads token remains private in official
Meta/Explorer handoff tabs, not persisted on server/configured in bot. Automatic
ad resolver/rollout not part of this proof; never claim every ad is accessible.
Sources: https://developers.facebook.com/docs/instagram-platform/reference/instagram-media
https://github.com/facebook/facebook-python-business-sdk/blob/25.0.0/facebook_business/adobjects/adcreative.py

## N11 automatic exact ad media, 2026-10-11

Root cause: an ADS referral ad_id cannot be resolved through the published IG
archive; the creative's source IG media can have a different permalink. Resolver
uses read-only Marketing ad/account/creative identity and effective IG candidate,
accepting source fallback only after exact permalink equality. Existing decoder
produces ten original frames and preserves caption/customer text/voice/photo in
one vision request; mismatch, expiry or access failure invokes honest fallback
and manager. No thumbnail guesses; dynamic creative without proven variant fails.

Owner explicitly approved never-expiring ads_read, private persistence and enabling;
completed another Meta email verification. Separate System User credential saved
privately outside Git; existing messaging credential unchanged. Actual Meta debug
checks valid matching app, expires_at=0, scopes exactly ads_read+public_profile.
Meta can still revoke access; no universal ad media access guarantee.

Meaningful red→green resolver/handler tests, 128 targeted and 813 full tests PASS;
Ruff/diff check/read-only code review clear. Native Windows decoder sandbox failure
resolved by rerunning the same checks with authorized native execution, keeping
network and DB guards. Rollout helper review found absent/partial new-file rollback
and unbounded accepted socket; corrected, isolated checks PASS and rereview clear.

Guarded server preflight verified 21 baseline and four staged files; backup verified
before apply. Apply/verify exit0, runtime manifest now22 verified files; source proof
retrieved exact ad VIDEO, ten original frames, caption617, no paid AI/client sends.
Server mocked success/failure/takeover routes PASS; local/public health status=ok,
ads_media.enabled=true/ready=true. No client history/pause/escalation reset. Safe
reports: n11-applied.json/n11-source-proof.json. Private credential retained on
rollback, runtime/config restore from verified backup. Optional live new-ad reply
has not been tested in this deployment; existing advertised source proved directly.

## N12 multiaccount access and unresolved incident, 2026-10-11

Actual referral120252331324000736 produced ad_graph_unavailable at18:35Z.
Direct Graph returned400/code100/subcode33; original Reader asset was only Б.
Owner approved ANALYZE-only К/С. Official Meta UI and /me/adaccounts verify all3,
with no broader campaign permissions. Exact ad.id filtered edges return200/empty
for all3; direct incident node still100/33. This does not prove deletion or another
owner. Actual incident source/video unavailable; owner cabinet/View ad link needed.

Compatible bounded CSV allowlist deployed, exact ad.account_id membership enforced
before creative, health validates every configured account. Same isolated credential,
Page/permalink/video safeguards preserved.31resolver/825full tests PASS, Ruff/diff
check/read-only reviews clear. Pytest testpaths fixes private credential traversal,
without weakening ACL or network/DB guards. Initial staged StoryMediaError did not
recur on repeat/guarded apply/final verify; its precise transient cause is unknown.

Two-file/config guarded backup/apply/verify PASS,22runtime hashes verified;
new PID/starttime13396→14524 confirmed before/after health read. Server CIM query
denied, replaced only rollout diagnostics with bounded netstat/Get-Process,
same preflight green. Local/public health enabled/ready; all3 access and previously
proven exact B video/10originalframes confirmed, no paid AI or client messages.
Reports n12-applied.json/n12-source-proof.json; no client resets/replay or personal
Facebook permission grant. Multiaccount support complete; incident remains open.

## N13 full incoming post and question, 2026-10-11

Root cause verified in actual incident: shared post arrived18:34:45Z, question
about visas with ADS context arrived18:34:46Z. First referral incorrectly compared
against absent prior referral, splitting5s batch into2dispatches. First visual
request saw post without question, second ad lookup failed100/33 and escalated.
Direct shared source17943390366326685 GET200/IMAGE matches owner-supplied permalink
Dci_ZT0s-3b; published767-item list excludes it, but explicit source is accessible.
Caption empty; actual full image preparation succeeds. This is not evidence of
Marketing ad ownership nor a reason to hardcode ad→post registry.

First referral now attaches to existing same-sender segment. Different explicit
referrals and silent boundaries retained. Full incoming shared post takes priority
over redundant Marketing dependency; customer question enters same vision request.
Unavailable fullpost falls back only to exact Marketing kind=ad and safe unavailable
reason codes. Identity/size/count errors and partialphoto substitutions fail closed.
History truthfully distinguishes originalpost failure from exactad fallback.
Standalone shared_sources path fixed; voice visual_parts path retains prior behavior.

17meaningful regressions,842fullpytest PASS/Ruff/diff-check/review clear. Reviews
found broad error catch, false history, partial-source fallback; red regressions
fixed before deployment. Initial partial-case notification assertion was incorrect
for existing flags-off fallback; verified actual preserved unavailable reply/noAI/
noadsource/no-manager behavior rather than changing that legacy route.

Guarded2file apply/verify exit0, backup and22runtime hashes verified, env unchanged;
new PID14524→12560/starttime confirmed before/after health. Local/public healthready.
Actual exactpost fullimage preparation verified; bothorder/primary/adfallback/both
failure/takeover server proof uses mockedAI/DB/messages, no client replay/reset.
Reports n13-applied.json/n13-runtime-manifest.json. Marketing ID still100/33;
N13 fixes incoming fullpost+question processing, not every ad-ID-only access failure.

## N14/N15: incomplete ad access and supplied-media priority (2026-10-11)

Eight real referral ad IDs audited:3accessible sources prepared(2videos10frames,
1photo),5Meta100/33. Fourth approved original disabled account ANALYZE assigned;
four-asset reads verified but missing5unchanged. Exact DELETED Insights queries
all4accounts200/empty; does not prove ownership or deletion. Additional owner-approved
personal account UI requires firstcampaignsetup; no further grants. Fourth asset
did not improve source coverage, so production env/allowlist unchanged.

Root cause independently found: enabled Marketing route masked actual supplied
referral post/photo/video whenever ad_id exists. N15 retains full incoming post
priority, then supplied referral post→clicked video/photo→exact Marketing source;
only availability failures continue. Identity/format/size guards stop, manager
abort checked between attempts. Clicked asset provenance explicitly avoids full
creative/carousel claim; URL presence logged as booleans only.

17new regressions,859fullpytest/Ruff/review PASS. Initial restricted fullrun3native
decoder failures resolved by required nativefilesystem access; exact3andfull859
passed without exclusions.3fileguardedrollout/backup/22hashes/envunchanged/newPID/
publichealth PASS. Real canonical known-ad decoder video10/photo1 proof is not
actual webhook URL presence evidence. Isolated source/fallback/guard/takeover and
N13pipeline mocks PASS; no paidAI/clientmessages/reset/replay. Reports n15-applied.json
and n15-runtime-manifest.json. Missing5ad-ID-only cases remain unresolved when no
provided media arrives; truthful fallback remains necessary.

## N16: preview bug and exact source recovery (2026-10-12)

Actual Elbrus ad120252561601750736 is readable in C, but three video_url referrals
stopped with invalid_media_url before Marketing. Official full ADS webhook example
calls video_url a THUMBNAIL; N15's full-video assumption is superseded.
https://developers.facebook.com/documentation/instagram-platform/webhooks/examples

Deployed fix:fullpost→exactMarketing→suppliedphoto; never video-decode video_url.
Identity/account/format/size/carousel/takeover guards remain. Named-catalog text
questions receive truthful unavailable-ad context and can be answered independently;
vague questions retain manager fallback. Safe URL-kind enums only, no raw URLs.
29new cases,888fullpytest PASS/8existingwarnings/33.43s,Ruff/diff-check/reviewPASS.
Review's Париж/ВДП/genericwinter and rollout reparse defects fixed red→green.
Guarded3file deployment/backup/env preserved/22SHA/PID6436→5188/local+publichealth
verified. Actual Elbrus10originalframes and mocked named/vague/takeover pipeline
PASS; no paidAI/messages/replay/reset/newgrants. Report:n16-applied.json.

Discovery:767published-media archive excludes all4 requested posts. Public HTML
og:image yields previews, not complete original/video/carousel guarantees. Branded
permalink edge returns400/code3 with both existing tokens. Boost reference only
documents active ORGANIC ads; empty results do not exclude old/hidden ads.

Official act_ACCOUNT/adcreatives lists are independent of unreadable Ad nodes.
Bounded scan:B1/K327exhausted,C1500over15pages(not exhausted),old0exhausted.
All four exact permalinks found in C. C ReadTimeout resolved by continuing only
unfinished accounts with20s timeout. No campaign writes/neighboring media downloads.
https://developers.facebook.com/docs/marketing-api/reference/ad-account/adcreatives
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py

Official Inbox Viewad + latestreferral log proves exact ad→post associations;
creative index and own IG GET verify exact original identity before preparation:

|Incoming ad ID|Exact post|IG media ID|Original preparation|
|---|---|---|---|
|120252486000870736|Dc_VvK9sXvD|17899850481366654|1image,134822bytes|
|120251635953870736|Dci_ZIesmOM|17964210927177587|1image,586160bytes|
|120252331324000736|Dci_ZT0s-3b|17943390366326685|1image,233574bytes|
|120252486000760736|Dc_VvpQgs8Y|18205133203365026|1image,601737bytes|

All4 strict permalink/full source preparations PASS; caption empty for all4.
Two helper assertions initially used wrong image capitalization/expected adapter
type; corrected to actual function contract, final probesPASS. Original JPEG/SHA
proof:n16-full-originals-proof.json; no AI/send/DB. Runtime registry not integrated.

Limits:7of8 observed sources now proved readable (3existingMarketing+4recovered).
Remaining120252486000910736 cannot be bound to latest Viewad: that client's newer
referral is120252331324000736. Historical original URL was not stored; no inference
from matching tour/latestad. No documented public Inbox Viewad or universal opaque
adID→permalink lookup found. Creative recovery needs an independently proved link.
Durable owned-ad registry/archive with exact IDs/permalinks/originals and complete
new-ad registration/updates is proposed, not implemented or universal coverage.
Canonical skill docs_check/skills_validate scripts absent in this project; no canon
or skill files changed. Project QA above applies to deployed fix; source evidence
is separate.

## N17: automatic source discovery, 2026-10-12

Owner rejects manual ad registration; N16 registry proposal is superseded.
Owner has no company Instagram login. Unrelated saved Instagram profile was not
used. Existing authorized Facebook Business Suite is available; no new grant,
credential export, persistent browser session, install, paid AI or client send.

Bounded live evidence:

- Five exact Ad and IGBoostMediaAd requests fail100/33 with both existing token
  families. All-status inventory excluding DELETED returns589ads (B1/K172/C416/
  old0), exhausted, no exact id/adset_id/source_ad_id match. DELETED explicitly
  rejected by endpoint; SDK field enum does not prove accepted filter values.
- Maximum historical ad-level Insights without status filter is200 in all four
  accounts. Known controls in B/C returned; five target IDs absent. Absence does
  not prove deletion, a different owner, or universal account completeness.
- C AdsManager exact331 filter and maximum37-month dates: no ads. Read-only UI.
- Logs contain220 text referral events for five IDs; zero standalone referrals,
  no post source, only3photoURL events. This disproves the proposed separate
  logged referral-event source for these cases, not every future payload shape.
- Connected Instagram accounts and known C creative return the configured
  company actor17841402218805629; no alternate company actor. IG authorized
  accounts with explicit company business parameter also100/33.
- Five exact message /shares reads200/data=[]/no pagination. This endpoint's
  Pages-only reference does not establish general Instagram CTD applicability;
  successful empty results do not recover Viewad.
- GET failed331/previews?ad_format=INSTAGRAM_STANDARD:100/33. Control Elbrus ad
  returns200/one HTML body iframe, no canonical source. Preview is not original.

Business Suite's visible UI has one global latest-ad link. Two historical
Melnikava ad markers have no per-message link or interactive ancestor. Newer331
cannot identify older910. A browser-assisted automatic lookup for a genuinely
latest incoming referral remains a candidate: verify client/current latest MID
and adID before/after lookup, reject intervening different-referral ambiguity,
then strict canonical IG/permalink original preparation. Exact unattended
correlation/authentication is not proved or deployed. No private backend/hidden
React state/cookie extraction was used. No claim of reading any advertisement.

Independent read-only identity review: the proposed before/after latest MID/adID
guard is insufficient. Global header freshness is not proven by unchanged
webhook state, username, matching text or date. Need a visible exact Ad ID or a
source link bound to the specific incoming message before automatic caching.
Four N16 original retrievals remain valid case evidence, not a general binding
algorithm. Current official Page/IG SDK has no get_ads reverse enumeration;
promotable posts/media do not supply incoming adID identity. No new API candidate
found. Automated universal recognition remains unresolved under current access.

Reports: n17-identity-probe.json, n17-insights-source.json,
n17-preview-message-probe.json; context-owner probe safe stdout. Production N16
source remains unchanged; its previous888pytest/Ruff/rollout evidence applies
only to that deployed fix, not to this unimplemented browser candidate.

Primary reference/SDK:
https://developers.facebook.com/docs/marketing-api/reference/adgroup/previews
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/ad.py
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adpreview.py
https://developers.facebook.com/docs/graph-api/reference/message/shares
https://developers.facebook.com/docs/marketing-api/reference/ad-account/insights
https://developers.facebook.com/docs/marketing-api/reference/ad-account/connected_instagram_accounts

## N18: silent advertising handoff, 2026-10-12

Owner supersedes general ad recognition work: any unclear ADS goes silently to
manager, including a readable creative, title-only context and no question.
Current customer named catalog subject, independent explicit tour-list/visa-
support request or confirmed recent same-ad dialog keeps ordinary answering.
Ad title alone is not customer context. Recent context is customer-derived,
same exact ad ID,12hours maximum, invalidated by a normal processed turn; private
session metadata only, no ad ID or signedURL added to conversational history.
Voice uses existing GigaAM words before the ad gate; unclear voice failure also
stays silent. Unsupported ADS files/products retain human routing silently.
Other ordinary files/media/voices and exact decoder guards are unchanged.

Parent separated the existing silent notification body from its processing-lock
wrapper, avoiding recursive-lock deadlock. Success/error/limit/profile failure/
takeover remain without client send/queue. Current phone only; short human
summary removes URLs. Standalone ADS is an event boundary and gets a stable
receipt hash when a valid timestamp exists, preserving dedup and nearby messages.

Meaningful regressions: initial18red→24green; source review found raw attachment
dispatch and generic exception reply bypasses. Four raw card tests red→green,
transient real session-read failurePASS. Missing MID dedup red→green.31newcases,
919fullpytestPASS/8pre-existingwarnings/33.14s; Ruff/diff-checkPASS. Superseded
vague-answer tests changed to silence; existing media/identity/guard tests retain
their assertions with an explicitly named customer subject. No tests skipped.

Guarded deployment two files only. Read-only rollout review found unguarded
manifest writes in apply/restore; corrected to checked paths before apply.
Helper compile/Ruff and final staged preflightPASS; backup/source manifest/env/
launcher/ads-token preserved. Apply stdout records applied=true, SSH exits1
during restart; treated as uncertain transport completion until verifyexit0
confirmed22runtime hashes and newPID5188→11348/start2026-10-11T23:19:34Z.
Local and publichealth enabled=true/ready=true. Same staged+installed mock
proofs silence/named/visa/failure/limit/takeover/card and standalone boundary/
dedupPASS. No real client sends, replay/reset, paid model call or new grant.
Report:n18-applied.json. Universal ad-source automation remains unproved and is
deferred by the new owner policy; N18 does not claim it is implemented.


## N19 — model decision replaces lexical ad clarity gate (2026-10-14)

Symptom: clear real ADS queries «Виза есть! Пришлите программу тура ВДП» and
«Здравствуйте. Есть ли у вас тур в Прагу в январе?» silently escalated. N18's
catalog-title/prefix gate did not recognize the acronym unless a catalog title
was exactly that acronym, and five-character prefixes mismatched Прага/Прагу.
It also risked false matches such as Познань/познакомиться. Owner explicitly
requires every eligible advertising request to reach DeepSeek, with clarity
judged by the model rather than another local dictionary.

Fix: remove lexical clarity functions and new ad_dialog_context writes. One
existing model invocation receives actual current text/history/catalog, safe
original media when obtainable, and explicit unavailable status otherwise. ADS
prompt has a final decision/reply/context JSON contract. Text ADS uses existing
JSON model factory; vision ADS uses existing vision model with the same contract.
Validated answer follows the normal response flow. Handoff invokes manager with
a short gist and returns before client sends/queues/receipts/phone acknowledgement,
even on notification limit/error. Invalid envelope/model failure is silent too.
Unsupported ADS files/products reach the model before mandatory human handling.
Story mentions retain silent no-model handling. Input/rate guards and manager
pause remain; rejected media bytes/unsafe input are not forwarded to DeepSeek.

Verification: initial29red/1green→30green; read-only source review found missing
failed-voice status beside typed text and visible post-STT guard response in ADS.
Both corrected with2red→3green;33new casesPASS. Final952pytestPASS/8existingwarnings/
50.61s, Ruff/diff-checkPASS and independent source review clear. Rollout reviewer
caught wrong visual mock shape; corrected to actual StoryMedia before preflight.
Guarded backup/two sources/22manifest hashes/env/launcher/ads-token preservation
verified. Apply stdout applied=true but SSHexit1 at restart; independent verify
exit0 confirmed installed hashes, newPID11348→8456/start2026-10-14T11:21:16Z,
local/publichealthok. Staged+installed13mock cases and standalone boundary/dedup
PASS. Safe report:n19-applied.json.

Limits: mock model responses prove routing and silence, not real DeepSeek
understanding. No paid live trial, client replay/reset or real manual external
messages. Universal exact advertisement retrieval remains unresolved; missing
content is explicitly unavailable to the model rather than invented.

## N20 — exact View ad source investigation (2026-10-14)

Read-only investigation; no runtime/configuration/permission changes or client
messages. The supplied old screenshot matches the Business Suite conversation
whose viewed-ad dialog names «Рилс ВДП Рождество» and links to DeI-3NiA_5L.
Current installed resolver independently reads ad120255819105930322 (HTTP200),
returns VIDEO/media17947642536299061/the same canonical permalink, and prepares
10 original-video frames plus649caption characters. This particular source is
readable now; no paid model call or customer response was exercised.

Negative control ad120252331324000736 remains HTTP400/code100/subcode33.
A newly tested official Ad Account activities route, filtered by exact oid and
category AD over2026-07-14..2026-10-14, returns zero rows in B/K/C/old accounts.
All four HTTP200/pagination exhausted. Positive control120252561601750736 in C
returns3 exact rows (create_ad/update_ad_run_status), proving endpoint/filter
work. This bounded absence does not prove deletion, ownership or universal
absence. Safe reports: n20-source-check.json and n20-activities-check.json.

Current official messaging webhook documentation (updated2026-09-16) identifies
ads_context_data.video_url as a video thumbnail, not the full original video.
Neither this payload nor the visible global latest-ad header proves a universal
per-historical-message View ad URL. N17 identity limitations still apply.

New partial candidate verified in Meta changelog2024-06-11: a comments webhook
for an ad/boosted post carries media.ad_id and original_media_id together.
These explicit pairs could build an automatic exact source index without manual
registration, but only after the relevant comment event is received; ads without
comments/earlier DMs remain uncovered. Not implemented or live-event verified.
Page subscribed_apps reports configured app fields=[messages]; the attempted IG
subscription read with the existing Facebook token returns400/code100, so IG
comments subscription status remains unknown, not proved absent.

Conclusion: this screenshot source is proved readable with existing code;
universal exact creative retrieval under current access remains unproved.
Do not add speculative mappings or claim comments/indexing solves every ad.
Existing N19 sends eligible customer text/context to DeepSeek even if ad media
is unavailable. Research notes only; no new source resolver deployed.

Primary references:
https://developers.facebook.com/documentation/business-messaging/instagram-messaging/webhooks/
https://developers.facebook.com/documentation/instagram-platform/changelog
https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adaccount.py
https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/main/facebook_business/adobjects/adactivity.py

## N21 — permissions and official boosted-media API audit (2026-10-14)

Owner rejects comment indexing; asks for missing official permissions. Read-only
UI/docs/server probes, no new grants/tokens/runtime changes/client messages.
Token debug200: SYSTEM_USER valid, correct app, expires_at0, ads_read+public_profile.
PAGE token valid/correct app/expiry0, instagram_basic/pages_read_engagement plus
existing messaging/business/page scopes, no ads_read. Scopes do not combine across
tokens. me/permissions granted; me/adaccounts returns all four cabinets, exhausted.
Runtime allowlist retains B/K/C; old cabinet access was exploratory and not added.
Business Suite shows Reader only four ANALYZE ad accounts and TEST on the app;
no assigned Page/IG. Company owns IG17841402218805629. Existing Facebook operator
has IG partial content/messages/community/ads/insights access. Developer console
shows Standard ads_read/instagram_basic/pages_read_engagement/business_management;
instagram_manage_messages and pages_manage_metadata Advanced. No required actions.
App roles UI confirms existing Facebook operator is Administrator and Sundita
Reader is Tester. A temporary USER-token experiment can therefore use the
existing operator's app role; new read scopes still require authorization.

Minimal GET /ad?fields=id succeeds for120255819105930322(B) and120252561601750736(C),
as does creative{id}; failed120252331324000736 remains100/33 already at id-only.
This is not a decoder failure or a denied expanded video field. It does not prove
deletion/ownership or that a broader permission would resolve the object.

NEW official IGMedia field/edge boost_ads_list returns associated ACTIVE boosted
advertisements (Facebook Login only), SDK IGBoostMediaAd(ad_id,ad_status,id).
This corrects any interpretation of N17 that NO reverse media-to-ad edge exists:
N17 checked IGUser/Page get_ads and direct boost nodes, not IGMedia boost_ads_list.
Live documentation IGMedia2026-08-12 and IGUser2026-04-22 require instagram_basic+
pages_read_engagement and ads_read OR ads_management if Page role came through BM.
Our split scopes differ from this documented combination; however live requests
already succeed partially, so missing combination is a hypothesis, not root cause.

Live boost probe: original17943390366326685 and originals17899850481366654/
18205133203365026 return id200 and boost200/empty/exhausted with BOTH tokens.
Working creative effective17947642536299061 returns id200 both; PAGE boost gives
100 'endpoint does not support ad media id input; use IG organic media id', while
ads token returns200empty. Its source18125669482848686 returns id200/boost200empty
with PAGE; ads-only token gives100/33 for both. No matching failed ad recovered.
Empty ACTIVE-only results are not proof of ownership/deletion or no historical
advertising. No positive nonempty boost result; general coverage unproved.

No evidence requires ads_management for this incident. Official IG requirements
permit ads_read, and existing direct-Ad controls work with it. business_management
supports business/system-user asset inventory; not a proven direct-Ad fix.
Permission Standard/Advanced differs from Marketing Limited/Full API tier; none
automatically grants an unassigned asset. A combined read-only token comparison
using the same company asset identity is a bounded next experiment, not a promised
fix; any new scope/asset authorization must be explicit and bot tokens preserved.

Safe evidence: n21-permissions-check.json, n21-boost-check.json,
n21-boost-organic-check.json. Helpers RuffPASS, live probes exit0, secrets excluded.
No product code changed or paid model invoked; universal ad retrieval unresolved.

Primary references (live official pages read in browser):
https://developers.facebook.com/documentation/instagram-platform/instagram-graph-api/reference/ig-user
https://developers.facebook.com/documentation/instagram-platform/reference/instagram-media
https://developers.facebook.com/documentation/ads-commerce/marketing-api/get-started/authorization
https://developers.facebook.com/docs/business-management-apis/system-users/guides/permissions
https://developers.facebook.com/documentation/development/permissions
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/igmedia.py#L170

## N22 — authorized combined USER-token comparison (2026-10-14)

Owner approved temporary Facebook USER token combining ads_read/instagram_basic/
pages_read_engagement. Used official Graph API Explorer, confirmed app1133220645701291
and USER identity Danila. New token remained in official Meta browser UI; not
copied to server, project, logs or production configuration. Initial automatic
browser snapshot unexpectedly exposed the pre-existing input token in tool output;
subsequent snapshots explicitly redact token values. Avoid full automatic Explorer
snapshots in future; do not echo that credential or revoke shared access casually.

Operational incident: selecting Clear then three scopes and Generate changed
existing user grants; original server PAGE debug lost pages_messaging and
pages_manage_metadata. This effect was not warned by the visible UI flow before
the change. Paused diagnostics, restored original seven requested scopes plus
approved ads_read through Explorer. USER me/permissions then showed all eight
plus public_profile granted, no declined; original PAGE debug confirmed previous
scopes restored and ads_read additionally propagated. SYSTEM_USER unchanged.
No production token value/file replaced. Do not use Clear to narrow a diagnostic
token on a shared production app; token/grant isolation was disproved here.

Final server verification: original PAGE GET page/id200, IG/id200,
page/subscribed_apps200 with configured app messages subscription retained;
localhost health200/statusok/ads_media enabled+ready. No send/replay was performed,
so absence of any transient delivery impact is not claimed. Safe report:
n22-live-health.json; restored metadata report n22-restored-permissions.json.

Actual USER comparison, Graph v26.0:
- failed120252331324000736 fields=id:100/subcode33 unchanged;
  Meta trace AHp4yiB4HX9wyOtBKQcIzD4 retained for a possible support case.
- control120255819105930322: id/account2748504208879634/creative1392757435898637
  readable with the same USER token.
- working organic18125669482848686 fields=id,boost_ads_list{ad_id,ad_status}:
  explicit pair to120255819105930322, ad_status=off. Earlier PAGE returned empty
  and ads-only SYSTEM_USER100/33. Combined USER access improves this control;
  token identity/assets also differ, so scopes alone are not isolated causally.
- problematic17943390366326685: id readable; boost field omitted; direct boost
  edge returns data[]. Further17899850481366654/18205133203365026/17964210927177587
  all return id only with boost field omitted. No failed ad mapping recovered.

Official docs describe ACTIVE ads; observed returned ad_status=off means do not
equate that documented object-status condition with current delivery on/off.
Conclusion: combined read permissions do not resolve the tested inaccessible Ad;
there is now a positive official reverse-mapping control but not universal access.
No ads_management grant, resolver change, deployment or manual source registry.
Next meaningful escalation is a Meta case comparing inaccessible referral ID
against readable control and UI visibility, not speculative wider write scopes.

## N23 — two clear ADS queries silently handed off (2026-10-15)

Owner explicitly authorizes log investigation only, no server changes. Used SSH
read-only file operations, Python -B/stdin with stdlib only and SQLite URI mode=ro;
no helper upload, bot import, restart, configuration/grant/client-data writes,
message replay, paid model or Meta API calls. Only local notes updated.

Correlated screenshot times (Minsk UTC+3) with exact current bot.log entries:
- 18:17:08 receipt/18:17:20 model response, @lebedev.e_ case. Saved user history
  is «Эльбрус». Ad120252561601750736 prepared10images; vision completed with
  input24827/output295 tokens. Immediately instagram.ad.invalid_model_decision,
  then successful Telegram notifications18:17:22..23. bot.log lines1258..1268.
- 18:58:27 receipt/18:58:46 response, @svetlana_rbim case. Saved user history is
  «Виза есть! Пришлите программу тура ВДП». Ad120255975320400322 prepared1image;
  vision completed with input19383/output288 tokens. Immediately same invalid
  decision warning, then Telegram18:58:47..49. bot.log lines1287..1297.
Both states have escalation_count1 and only actual user turn (no assistant reply).

Installed main/llm/prompts SHA match local expected N19 runtime exactly. Both
calls reached DeepSeek with prepared images; no advertising-read failure shown.
Known failure is main._parse_ad_response returning None followed by exact generic
notification at main1013..1015 and silent return at1164. This is not evidence that
the model judged the customer question unclear; no valid decision was accepted.

Likely contributing implementation defect: media ADS selects get_vision_llm,
which has no response_format=json_object, unlike text ADS get_llm_json. Vision
JSON is requested only in the prompt; parser requires an exact three-string-key
object plus strict lengths and decision/reply/context constraints. Any ordinary
text, extra formatting/keys or inconsistent envelope causes generic handoff.
Raw output, rejection category and finish_reason are not recorded, so exact
malformation cannot be established retrospectively. Output295/288 is well below
2048; no evidence supporting output-budget truncation in these two incidents.

Conclusion: confirmed response-contract rejection after successful media/model
processing, not failed ad access. No fix or deployment performed. Any follow-up
repair should protect both media and text ADS contracts and preserve actual gist
on technical fallback; separate authorization/scope applies to implementation.

## N24 — local ADS response-contract repair (2026-10-15)

Owner approved proposed four-point repair. Spec written before implementation;
no server actions, token/config changes, messages or paid model calls. DeepSeek
official JSON/Vision/ChatCompletions docs support deepseek-flash image inputs,
thinking disabled and response_format=json_object; prompt JSON/examples exist.
get_vision_llm has opt-in json_mode, used only for ADS; ordinary vision unchanged.

Whole-response bare/fenced JSON is accepted after whitespace/fence normalization.
Strict schema, duplicate/extra/type/length/decision constraints remain. Logs carry
fixed rejection code and allowlisted finish/type/length/token metadata only;
finish_reason=length rejects even an otherwise parseable envelope. Provider
failure uses the same silent technical path without raw exception/model logging.
Manager gist states technical failure and sanitized actual current question;
phone stays in its dedicated field, links/raw output/old history do not enter gist.
No local intent classifier or extra model invocation/retry was introduced.

Verification: after fixing fixture import, initial25red/1green. Implementation
then58green/1red exposed text-provider fallback's absent media dereference; fixed
and59green, plus metadata privacy regression for27newcases/60targetedPASS.
Independent read-only review clear and independently60targetedPASS. Full sandbox
run976PASS/3native Windows decoder failures. Outside-sandbox default tmp directory
had ACL rejection; same native tests3PASS with fresh tmp, then full979PASS/8existing
warnings/37.57s. No tests skipped or weakened for environmental failures. Ruff and
diff checkPASS. No live semantic understanding claimed; original bad model
responses were not logged, so exact historical malformation remains unknown.

Changes ready locally, not deployed. Production still has N19 until a separate
authorized rollout; preserve this distinction in status reports.

Primary sources:
https://api-docs.deepseek.com/guides/json_mode/
https://api-docs.deepseek.com/guides/vision/
https://api-docs.deepseek.com/api/create-chat-completion/

N24 authorized rollout (2026-10-15): owner requested deployment. Reused guarded
N19 helper adapted strictly to main.py/llm.py, new bundle/backup/state names,
staged module imports and18mocked scenarios including actual image/video input,
JSON factory flag/body, whole fences, truncation/provider fallback and real gist.
Syntax/Ruff/independent read-only rollout review/preflightPASS. Baseline22hashes
and staged2SHA verified; backup/source+manifest/env/launcher/ads-token preservation
verified before scheduled restart. No dependency/config/credential/client-data
update, real model call or manual message.

Apply stdout applied=true, SSHexit1 during restart; treated as uncertain transport
until independent verifyexit0. Confirmed22installed hashes, PID8456→17644/start
2026-10-15T17:35:57.4094983Z, localhealthok/enabled+ready, installed18mocked cases
plus standalone boundary/dedupPASS. Public PowerShell request timed out and web
fetch was unavailable; native curl independent GET returned200/statusok/adsready.
No speculative reapply or rollback. Local canonical manifest updated exactly the
two deployed entries and retained20others. Safe reports:n24-applied.json and
n24-runtime-manifest.json; recoverable backup:n24-backup. Production now N24;
the earlier local-only paragraph describes the pre-authorization phase.
