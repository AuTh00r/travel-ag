# Cloud SSH access — setup scope (2026-10-26, before configuration changes)

Intent: configure the existing Codex Cloud environment for travel-agent-bot so
cloud tasks can connect to the existing Windows server through its approved
Cloudflare/SSH access. Reuse the user's earlier environment/setup conversation;
do not create duplicate environments or replace existing repository setup.

Boundaries: inspect current environment network/credential readiness, existing
install/start instructions, and supported SSH transport. Only the intended
private environment and required setup artifacts may change. Keep credentials
masked, out of logs/source control/published filesystem. Do not alter bot code,
client data, production restart tasks, server authentication policy, public ports,
or the environment's audience. New persistent credentials/expanded access and
messages to a separate setup conversation require applicable authorization.

Acceptance: distinguish local SSH success from actual cloud verification; test
from the cloud executor with a read-only command, verify server host identity
without disabling host-key/TLS checks, record dependencies/secret names/network
requirements, preserve unrelated environment fields. Publish the prepared setup
when authorized and verify a fresh execution context. Report missing platform
capabilities/access honestly; do not claim configured credentials imply readiness.

## Verification in progress (2026-10-26)

- The previous setup build cannot resume: the platform reports that it was deleted.
  Reopened Edit on the existing `travel-ag` environment; no duplicate environment
  was created. The new setup conversation is `01a1794c-c613-766f-9a56-d7fc3be020e1`.
- User authorized messaging the setup conversation. The new cloud execution has
  started; the three existing credential variables are present. This is not proof
  that their credentials are accepted by Cloudflare or SSH.
- Correct SSH account: `deploy`; the previous cloud configuration used `root`.
- Pin the previously verified server ED25519 host key; keep strict host-key and
  TLS validation. Reconstruct private keys only temporarily and remove them.
- Cloudflare documents service-token variables for `access ssh`, and requires
  a Service Auth policy for unattended authentication. Existing policy and token
  validity still require verification; HTTP 302 alone does not identify the cause.

References:
- https://learn.chatgpt.com/docs/environments/cloud-environments
- https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/
- https://github.com/cloudflare/cloudflared/blob/master/_autodocs/api-reference/access-command.md

## Verified access (2026-10-26)

Cloudflare UI inspection confirmed that the SSH application previously had only
an email-based Allow policy. The enabled existing service token had no Service
Auth policy on that application. User explicitly approved adding only this token.

Added `Codex Cloud SSH`, action `Service Auth`, Include `Service Token` =
`service_token_cloudflare`, policy `551d319b-519e-4886-a655-b50836ac5390`, to
`ssh.sundita.online`. The existing email policy is preserved; no token rotation,
broader selectors, protection exceptions, or production changes were performed.

Cloud execution verified SSH exit 0 at **2026-10-26 17:59:35–17:59:37 UTC**:
`whoami` returned `sst\\deploy`, `C:/travel-agent-bot` exists, `/health` returned
`ok`. Existing credentials, normal proxy, and pinned host key were used; the
temporary private key was removed. Previous HTTPS probes had returned 403/1010;
this did not require disabling or bypassing any Cloudflare protection.

The setup draft audit passed: repository binding and dependencies preserved,
141 packages compatible, official cloudflared 2026.10.4 checked against pinned
SHA256, helpers persisted without secret values. A search of ordinary workspace
and temporary files found no credential-value matches; platform mounts and
symlinks were excluded. Helpers reconstruct a key temporarily at runtime and
clean it up. No bot startup, deployment, main import, or database initialization
is included in install/start instructions. The draft was saved and publication
started through the supported UI.

Publication completed through the supported UI. The platform inserted its
publication-complete message and loaded a new draft from the published version.

User explicitly approved one new read-only test cloud chat after publication.
Two attempts to create it failed before execution: desktop `thread/start` on the
durable host returned `-32603`, `grpcStatusCode=6`, at 18:10:13 and 18:12:38 UTC.
The platform request reference was `79bb9f39-95bb-41d0-ab93-85688e59a39b` in both
failures. No new test thread was registered by `list_threads`. These are chat
creation failures, not failed SSH operations. Their underlying platform cause
is unconfirmed. Do not claim a new regular cloud chat was verified.

Post-publication restoration was verified in the editor's replacement runtime:
runtime binding differed from the original and matched its local runtime; PID 1
started after the earlier check. The previous boot ID was not recorded, so no
boot-ID comparison is claimed. Helpers were restored and the pinned cloudflared
SHA256 matched. A single SSH check at **18:13:49–18:13:52 UTC** returned exit 0,
`sst\\deploy`, directory present, and `/health=ok`; the temporary key was removed.
No second publication or production mutation was performed. Published access and
restoration are verified; creation of a regular new cloud chat remains a separate
platform limitation, with the failed attempts above retained as evidence.
