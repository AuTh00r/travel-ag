# Five seconds of silence for inbound collection

Date2026-11-04. User authorized only the quiet-window change, then deployment.

Symptom: a post opens a fixed5s batch and a repeated question after that boundary
becomes another job. Distinct MID are distinct events; this is not webhook replay.

Change: legacy cancels and replaces only its waiting collector, atomically before
yielding. Prior collector cleanup checks ownership; running AI has already removed
its collector entry and is not cancelled. Every new MID restarts five seconds.
Recovery chooses the earliest contiguous prefix by receipt time with gaps<=5s;
the prefix becomes ready at its last receipt+5. A gap>5s remains a boundary even
after worker delay. SQLite receipts survive restart; same MID never changes time.

Unchanged: identical text is retained, existing merge/media/human routing, budget,
manager takeover, delivery receipts/unknown, flags and recovery intervals. A stream
every4s keeps waiting until five seconds of silence; no maximum wait was added.

Verification:3initialRED,143profilePASS,1815fullpytestPASS/8existingwarnings/98.73s;
Ruff/diffPASS. Read-only review found no blockers. Tests cover0/4/8→13, separate
quiet gaps, late worker, restart, MIDretry, independent clients, post+two equal
questions→one job, old collector cleanup, manager after timer reset, running AI.

Evidence: .kiro/specs/inbound-recovery/{requirements,design,tasks}.md TSK-033;
.kiro/decisions/0021-inbound-quiet-window.md. No server, paid calls or messages used.

Deployment04Nov01:09Minsk: only main.py/db/inbound.py from fresh server baseline.
Pending N42 SDK fix excluded;36manifest hashes verified. Candidate143PASS,
normal/partial/post-restart inversePASS. Package
c9799ee62db464aa07ee8b5be811b647f8f76ea20eb707be88730a3432ba3da9.
PID8248→18728, start03Nov22:09:03.2978786UTC. Prepare/apply/verify/postflight0.
Backup verified; inverse never restores live SQLite. Postflight01:16Minsk:
local/publichealth200ok, integrityok, errors/warnings0, unassigned/sending/unknown0.
All1550oldreceipts/27terminaljobs preserved;1836sessiondigests unchanged and
1legitimate fresh-input change, all1837retained. Scopeall/env/credentials/baselines/
catalog8 unchanged. Installed memory-only0/4/8→13PASS; no manual model calls/sends.
urllib public probes got Cloudflare403/1010; standard unmodified HTTPX200 from
client and server. Security rules and authorization were not changed.
