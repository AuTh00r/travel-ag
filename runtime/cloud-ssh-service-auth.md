# Cloud SSH: service-token routing (2026-10-26)

## Symptom

Cloud tasks had the SSH private-key variable and Cloudflare service-token
variables, but could not reach the SSH server. Earlier attempts redirected to
Cloudflare login; a later HTTPS probe returned 403 with Cloudflare error 1010.
Local interactive SSH worked, which did not establish unattended cloud access.

## Investigation

The existing SSH Access application had one Allow policy using an email identity.
It had no Service Auth policy. The existing non-expiring service token was enabled
and showed Not Seen Yet. Service-authentication logs contained no matching events.
Those observations did not alone identify the source of every earlier HTTP error.

## Fix and verification

After explicit authorization, added a separate Service Auth policy allowing only
the existing service token to the SSH hostname; preserved email login. No token
rotation, broad allow rule, WAF exception, proxy bypass, TLS relaxation, or server
configuration change was required.

At 2026-10-26 17:59:35–17:59:37 UTC, the managed cloud executor completed SSH with
exit 0 using the existing credentials, normal proxy, the `deploy` account, and the
previously verified pinned ED25519 server key. The server returned its expected
account, the bot directory existed, and its health endpoint returned `ok`.
Temporary private-key material was deleted after the check.

## Boundaries

Publication completed. The editor then received a replacement runtime (different
runtime binding, PID 1 started after the previous check). Its restored helpers and
pinned binary digest were verified. One SSH check at 18:13:49–18:13:52 UTC again
returned exit 0, expected account, directory present and health `ok`; the temporary
key was removed. The previous boot ID was not captured, so boot-ID comparison is
unknown.

Two attempts to create a separate regular test chat failed in Codex `thread/start`
before any SSH execution (`-32603`, `grpcStatusCode=6`). This is not evidence of an
SSH failure. The new regular-chat creation path remains unverified; do not claim
it worked just because the replacement editor runtime did.

- A successful editor session does not prove the published environment works in
  a fresh executor; publication and verification must be recorded separately.
- Keep private keys and service-token values out of source, logs, install/start
  text, and published files. Materialize keys temporarily with mode 0600.
- A service token being present does not mean an Access policy accepts it.
- Do not infer that 403/1010 requires disabling protections: the validated
  Service Auth configuration was sufficient for this SSH test.
- Bot deployment, production restart, and production database mutations are
  outside this setup scope.

References:
- https://learn.chatgpt.com/docs/environments/cloud-environments
- https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/
- https://github.com/cloudflare/cloudflared/blob/master/_autodocs/api-reference/access-command.md
