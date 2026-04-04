# Handoff

## Purpose

This file captures the current working state of `kerio-logstash-project` so work can continue quickly in another chat or shell session.

## Current Snapshot

- Updated: 2026-04-04 10:08 UTC
- Repository: `/root/kerio-logstash-project`
- Branch: `main`
- Latest tagged release: `v0.1b.3`
- Runtime ELK host: `10.4.29.70`
- Runtime Kerio host: `10.4.29.71`
- Syslog input: live Kerio RFC5424 syslog on `5514/udp` and `5514/tcp`
- File-based test input: removed

## Stack State

Remote stack on `10.4.29.70`:

- `kerio-elasticsearch`: `Up (healthy)`
- `kerio-kibana`: `Up`, published on `http://10.4.29.70/`
- `kerio-logstash`: `Up`, listening on `5514` and `9600`

Remote Kerio on `10.4.29.71`:

- `kerio-connect-lab`: `Up (healthy)`
- SMTP and admin ports are published and working
- External syslog is already pointed at the ELK host

## Latest Validation

Final end-to-end validation was completed on 2026-04-04.

Test message:

- Subject: `KERIO-FINAL-20260404-100321`
- Queue-ID: `69d0e1e9-00000003`
- From: `lab@example.net`
- To: `doge@kerio.lo`

Observed path:

1. Kerio `mail.log` on `10.4.29.71` recorded both `Recv` and `Sent`.
2. `kerio-logstash` on `10.4.29.70` emitted an aggregated `message_flow_aggregated` event.
3. Elasticsearch on `10.4.29.70` stored the parsed result in `kerio-flow-2026.04.04`.

Validated fields:

- `event.action=message_flow_aggregated`
- `event.outcome=success`
- `email.local_id=69d0e1e9-00000003`
- `email.subject=KERIO-FINAL-20260404-100321`
- `email.from.address=lab@example.net`
- `email.to.address=[doge@kerio.lo]`
- `kerio.recv_count=1`
- `kerio.sent_count=1`

## Release State

- Latest release in this repository: `v0.1b.3`
- Release content includes the live syslog-only workflow, the Kerio mail parser fix, and release tracking docs

## What Changed In This Session

- Removed the old `testdata/syslog_anonymized.txt` input path from the Logstash pipeline.
- Removed the `./testdata:/testdata:ro` mount from `docker-compose.yml`.
- Kept the live mail parser fix for Kerio events where `process.name=kerio`.
- Added a `Recv` grok variant for the live format where `Subject` comes before `Msg-Id` and `SSL` may be omitted.
- Updated `README.md` for the live syslog workflow and Kibana on host port `80`.
- Rebuilt the changelog into release-based sections with an `Unreleased` section for current work.
- Added `HANDOFF.md` and `NEXT_STEPS.md`.

## Suggested Resume Commands

```bash
cd /root/kerio-logstash-project
git status
ssh root@10.4.29.70 'cd /root/kerio-logstash-project && docker compose ps'
ssh root@10.4.29.70 'curl -s http://localhost:9600/_node/pipelines?pretty'
ssh root@10.4.29.70 'cd /root/kerio-logstash-project && source .env && curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/kerio-flow-*/_search?pretty -H "Content-Type: application/json" -d "{\"size\":5,\"sort\":[{\"@timestamp\":\"desc\"}]}"'
```
