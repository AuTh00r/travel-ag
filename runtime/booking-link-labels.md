# Booking link labels

2026-11-01. Two original DOCX programmes contained URLs labelled «ссылка на тур
на сайте». Downloaded plain text already included them, but the case-sensitive
booking-label regex did not recognize them. This was not cache staleness.

Shared label matcher now ignores case, accepts site/tour/link and booking labels,
prefers explicitly labelled booking links, and excludes programme Docs/Drive URLs.
Snapshot, rendered catalogue and whole-tour bootstrap use the same selection.
Legacy aggregate DOCX boundaries remain explicit; no generic-title heuristics.

Verification:1728pytest PASS,149profile PASS, Ruff/diff/read-only review PASS.
Actual8programme snapshot rebuilt offline6 ->8URLs, previous6unchanged.
Deployed after explicit approval:2files,36manifest entries; automatic sync
confirmed8/8links. Health/schema PASS,1711old sessionstates/1131receipts retained.

Rollout guard found existing tour_loader absent from the previous manifest.
Captured its physical SHA separately, verified/backed it up, then registered it.
Isolated inverse proof covers this existing-but-unregistered case: restore the
old file and prior manifest; never delete it as a presumed newly created module.
