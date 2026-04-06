# Handoff

## Purpose

This file captures the current working state of `kerio-logstash-project` so work can continue quickly in another chat or shell session.

## Current Snapshot

- Updated: 2026-04-06 12:50 UTC
- Repository: `/root/kerio-logstash-project`
- Branch: `main`
- Latest tagged release: `v0.1.5`
- Runtime ELK host: redacted from repository; use your local inventory or SSH alias
- Runtime Kerio host: redacted from repository; use your local inventory or SSH alias
- Syslog input: live Kerio RFC5424 syslog on `5514/udp` and `5514/tcp`
- File-based test input: removed

## Stack State

Remote ELK stack:

- `kerio-elasticsearch`: `Up (healthy)`
- `kerio-kibana`: `Up`, published on the ELK host HTTP endpoint
- `kerio-logstash`: `Up`, listening on `5514` and `9600`

Remote Kerio stack:

- `kerio-connect-lab`: `Up (healthy)`
- SMTP and admin ports are published and working
- External syslog is already pointed at the ELK host

## Latest Validation

Final end-to-end validation was completed on 2026-04-06.

Test message:

- Run ID: `LIVE-PLUS10-20260406-124549`
- Batch size: `20`
- Managed mailboxes created for the run: `10`
- Managed aliases created for the run: `10`

Observed path:

1. Kerio admin JSON-RPC created managed test users and assigned additional email addresses through `Users.set`.
2. Kerio `mail.log` on the Kerio host recorded `Recv`, `Sent`, and expected unknown-recipient failures for the batch.
3. `kerio-logstash` on the ELK host emitted aggregated `message_flow_aggregated` events after the aggregate timeout window.
4. Elasticsearch on the ELK host stored raw negative events in `kerio-connect-2026.04.06` and aggregated message flow in `kerio-flow-2026.04.06`.

Validated fields:

- `event.action=message_flow_aggregated`
- `event.outcome=success`
- `email.subject=KT-LIVE-PLUS10-20260406-124549-*`
- `email.from.address=<managed-or-control-mailbox@kerio.lo>`
- `email.to.address=[<managed-or-alias-mailbox@kerio.lo>]`
- `kerio.result=not_delivered` for standalone nonexistent-recipient probes
- Verification summary: `planned_messages=20`, `sent_messages=18`, `passed=20`, `failed=0`, `unparsed_hits=0`

## Release State

- Latest release in this repository: `v0.1.5`
- Release content includes the live syslog workflow, managed Kerio API provisioning for run identities, safer rerun cleanup, JSON-only run artifacts, the tuned mail-test toolkit defaults, and the family-standard project documentation

## What Changed In This Session

- Removed the old `testdata/syslog_anonymized.txt` input path from the Logstash pipeline.
- Removed the `./testdata:/testdata:ro` mount from `docker-compose.yml`.
- Kept the live mail parser fix for Kerio events where `process.name=kerio`.
- Added a `Recv` grok variant for the live format where `Subject` comes before `Msg-Id` and `SSL` may be omitted.
- Updated `README.md` for the live syslog workflow and Kibana on host port `80`.
- Rebuilt the changelog into release-based sections with an `Unreleased` section for current work.
- Added `HANDOFF.md` and `NEXT_STEPS.md`.
- Removed concrete lab IP addresses from repository-tracked files.
- Added a mail-test toolkit scaffold under `scripts/` for identity generation, batch SMTP sending, and run verification.
- Smoke-tested the new toolkit with a generated `MAILLOG-SMOKE` manifest and a `--dry-run` batch send.
- `generate_identities.py` now generates a unique random 12-character password per mailbox by default, with mixed case, digits, and special characters.
- Generated passwords now avoid fragments from the login, domain, and display name and use a narrower Kerio-safe symbol set.
- `generate_identities.py` now also supports automatic Kerio provisioning through the admin JSON-RPC API, so managed test users and their additional email addresses can be created without manual CSV import or UI alias entry.
- Managed run identities now use a deterministic run-based prefix plus a stable seed derived from `run_id`, which avoids collisions with pre-existing lab accounts and makes repeated runs reproducible.
- Managed Kerio cleanup now waits for asynchronous user deletion to finish before continuing, which prevents same-`run_id` delete/recreate races on live reruns.
- Generated run artifacts no longer include legacy CSV exports because the active toolkit consumes only `identities.json` and `kerio_provisioning.json`.
- `verify_run.py` now uses recipient-plus-time-window fallback correlation for negative cases such as unknown recipients and can infer raw failure classes from message text when `event.action` is missing.
- The real Kerio batch run `MAILLOG-KERIO-DEFAULT-20260404-1539` now verifies cleanly with `passed=100`, `failed=0`, and `unparsed_hits=0`.
- Raw negative-delivery Kerio events now parse correctly even when they arrive as `process.name=kerio`; Elasticsearch documents now include `email.from.address`, `email.to.address`, `event.action=delivery_unknown_recipient`, `event.outcome=failure`, and `kerio.result=not_delivered`.
- Live proof event: a synthetic nonexistent recipient in the lab domain at `2026-04-04T16:09:28Z` was stored in `kerio-connect-2026.04.04` with explicit non-delivery fields.
- Added `CONTRIBUTING.md`, `SECURITY.md`, `SUPPORT.md`, and `LICENSE` so the repository matches the project-family governance baseline.
- Reworked `README.md` to the common project-family structure with a copy-paste Quick Start, example input/output, verification checklist, troubleshooting section, and explicit governance cross-links.
- Replaced the old GitHub Actions `pylint` workflow with `.github/workflows/ci.yml`, which now covers static checks, Docker Compose validation, Logstash config validation, and a synthetic end-to-end smoke test against Elasticsearch.
- Switched the CI smoke-test probe from UDP to TCP on `5514` after confirming that TCP indexing is more deterministic in the local validation environment while still exercising the same Kerio parser path.
- Locally validated the new smoke-test logic with a synthetic RFC5424 packet for `sender.tcp@example.test -> ghost.user.tcp@example.test` and confirmed the indexed event fields match the workflow expectations.
- Added the project-standard GitHub Actions badge to the top of `README.md`, matching the documentation style used in the sibling `kerio-connect` repository.
- Fixed the GitHub Actions smoke-test step after the first remote run exposed a heredoc shell syntax bug in the Elasticsearch polling loop; the workflow now uses a stable `python -c` assertion instead.
- Fixed the GitHub Actions smoke-test Elasticsearch lookup after the next remote run showed that the synthetic document was indexed correctly but the `query_string` search remained too brittle; the workflow now uses exact `term` filters on keyword fields.
- Fixed the GitHub Actions smoke-test startup race after the next remote run showed that the synthetic event could still be sent before Logstash finished binding `5514/tcp`; the workflow now waits for both the pipeline API and a successful TCP connection.
- Fixed the GitHub Actions smoke-test polling body after the next remote run showed the synthetic event was already indexed but the `_search` request was sending malformed JSON due to over-escaped content inside `curl -d`.
- Tightened the GitHub Actions smoke-test readiness check again after the next failed release run showed that a TCP connect probe could still pass before Logstash actually started the `tcp` input listener; the workflow now waits for the explicit `Starting tcp input listener` log entry and then pauses briefly before sending the probe.

## Suggested Resume Commands

```bash
cd /root/kerio-logstash-project
git status
ssh root@<elk-host> 'cd /root/kerio-logstash-project && docker compose ps'
ssh root@<elk-host> 'curl -s http://localhost:9600/_node/pipelines?pretty'
ssh root@<elk-host> 'cd /root/kerio-logstash-project && source .env && curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/kerio-flow-*/_search?pretty -H "Content-Type: application/json" -d "{\"size\":5,\"sort\":[{\"@timestamp\":\"desc\"}]}"'
```
