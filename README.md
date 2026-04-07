Language: [English](README.md) | [Русский](README.ru.md)

# Kerio Connect Logstash Project

A reproducible Logstash and Elasticsearch lab: it receives Kerio Connect syslog, maps it into understandable fields, and helps trace a message from receipt to delivery.

[![CI](https://github.com/foksk76/kerio-logstash-project/actions/workflows/ci.yml/badge.svg)](https://github.com/foksk76/kerio-logstash-project/actions/workflows/ci.yml)

> **Project status:** A lab-friendly project for safely checking Kerio Connect log parsing before live use.

> **Language policy:** `README.md` is the main English README. `README.ru.md` is a helper Russian translation for lab work and onboarding.

## Why this repository exists

Kerio Connect can send useful operational, security, and mail-delivery events over syslog. In their raw form, though, those logs are not very pleasant to search, graph, or test repeatedly.

This repository has two jobs:

- receive live Kerio Connect syslog, parse Kerio log lines, and store them in Elasticsearch as structured events;
- provide a local lab where the parser, mail flows, and audit events can be checked before a live server is connected.

## Project family

This repository is part of the **Kerio Connect Monitoring & Logging** project family:

1. [kerio-connect](https://github.com/foksk76/kerio-connect) — reproducible Kerio Connect lab environment
2. [kerio-logstash-project](https://github.com/foksk76/kerio-logstash-project) — parser and storage pipeline for Kerio syslog
3. [kerio-syslog-anonymizer](https://github.com/foksk76/kerio-syslog-anonymizer) — deterministic anonymization of real log data for safe public use

## Where this repository fits

In the overall chain, this repository sits between Kerio Connect and the viewing layer:

`Kerio Connect -> Syslog (RFC5424) -> Logstash -> Elasticsearch -> Kibana / Grafana`

The repositories complement each other:

- `kerio-connect` provides a reproducible Kerio Connect lab;
- `kerio-syslog-anonymizer` prepares real logs for safe public sharing;
- this repository covers the Logstash / Elasticsearch part for Kerio syslog.

## Main Usage Flow

The usual path is:

1. Kerio Connect sends syslog to `5514/udp` or `5514/tcp`.
2. Logstash parses Kerio `audit`, `security`, `warn`, `operations`, and `mail` logs into ECS-like fields.
3. `Recv` and `Sent` mail events with the same `Queue-ID` are grouped into one message-flow document.
4. Elasticsearch stores original events and aggregated mail flows for search and inspection.
5. The scripts in this repository run repeatable mail, audit, and indexing checks.

## Who This Is For

- Kerio Connect administrators who need to understand what happened with mail, logins, and delivery failures.
- DevOps, observability, and SecOps engineers who want a small ELK stand for searching, validating, and troubleshooting Kerio logs.
- Project contributors who want to change the parser and immediately see what changed in the indexes and test runs.

## Architecture / Component Roles

The same components, by role:

1. **Kerio Connect** sends RFC5424 syslog to port `5514`.
2. **Logstash** reads the syslog wrapper and applies Kerio rules from `logstash/pipeline/kerio-connect-main.conf`.
3. **Elasticsearch** stores two kinds of data: original events in `kerio-connect-*` and mail flows in `kerio-flow-*`.
4. **Kibana / Grafana** provide search, inspection, and future dashboard views.
5. **Scripts in `scripts/`** create test users, send mail, and verify that events reached the indexes.

## Requirements

### Software

- Debian, Ubuntu, or another Linux environment with Docker support
- Docker Engine
- Docker Compose plugin
- `curl`
- `python3` for the local verification example and helper scripts
- A Kerio Connect host if you want to test with real Kerio logs instead of synthetic events

### Hardware

- 2 vCPU minimum
- 6 GB RAM available to Docker is a practical minimum for the default settings
- 10 GB free disk space for images, Elasticsearch data, and logs

### Tested versions

| Component | Version | Notes |
|---|---|---|
| OS | Debian GNU/Linux 13 (trixie) | Current maintainer environment |
| Python | 3.13.5 | Used for helper scripts and synthetic input |
| Docker Engine | 28.2.2 | Known good |
| Docker Compose | 2.37.1 | Known good |
| Elasticsearch | 8.19.11 | Defined in `docker-compose.yml` |
| Logstash | 8.19.11 | Defined in `docker-compose.yml` |
| Kibana | 8.19.11 | Defined in `docker-compose.yml` |

## Repository structure

If you need to find something quickly:

- `docker-compose.yml` starts the local Elasticsearch, Logstash, and Kibana stack.
- `logstash/pipeline/kerio-connect-main.conf` is the main Kerio parsing pipeline.
- `logstash/config/` contains Logstash settings and the pipeline list.
- `elasticsearch/templates/` contains index templates for `kerio-connect-*` and `kerio-flow-*`.
- `docker/kibana/` contains helper scripts for starting Kibana with a service token.
- `scripts/` contains run tools: test-user generation, mail sending, audit matrix, and verification.
- `artifacts/runs/` is for local run artifacts; its contents should stay out of git.
- `README.md`, `README.ru.md`, `CHANGELOG.md`, `HANDOFF.md`, and `NEXT_STEPS.md` describe the current project state and next steps.

## Documentation language policy

- `README.md` is the main English source.
- `README.ru.md` is the Russian translation for lab work and quick onboarding.
- The first line of both README files is the language switcher.
- The Russian README follows the English README and does not document separate behavior.
- `CHANGELOG.md` is maintained in English.
- `CONTRIBUTING.md` is maintained in English; Russian README changes are welcome when they keep the meaning of the English version.

## Quick Start

Short path: start the local stack, send one test event, and see it in Elasticsearch.

By the end, you will:

- start the ELK stack;
- confirm that the Logstash pipeline is loaded;
- send one syslog event to Logstash;
- see the parsed Kerio event in Elasticsearch.

### 1. Clone the repository

```bash
git clone https://github.com/foksk76/kerio-logstash-project.git
cd kerio-logstash-project
```

If all is well:

- the current directory is the repository root;
- files such as `docker-compose.yml` and `README.md` are present.

### 2. Prepare the environment

Create `.env` with the Elasticsearch password for this stack:

```bash
cat > .env <<'EOF'
ELASTIC_PASSWORD=ChangeMe-2026!
EOF
```

What you can edit:

- replace `ChangeMe-2026!` if you do not want to keep the example password;
- keep the variable name exactly `ELASTIC_PASSWORD`.

What matters:

- `.env` must exist before `docker compose up -d`;
- the same password must be used for all `curl -u elastic:$ELASTIC_PASSWORD ...` commands below.

Optional settings for live Kerio test runs:

```bash
KERIO_API_USER=admin@example.test
KERIO_API_PASSWORD=ChangeMe-2026!
```

`scripts/generate_identities.py` uses these values when you want the test tools to create and reset managed Kerio mailboxes through the admin API.

Before the first start, check the memory settings:

- `docker-compose.yml` currently sets `ES_JAVA_OPTS=-Xms2g -Xmx2g` and `LS_JAVA_OPTS=-Xms1g -Xmx1g`;
- if your Docker host cannot spare that memory, lower those values in `docker-compose.yml` before you start the stack.

### 3. Run the project

Start the stack:

```bash
docker compose up -d
```

Install the Elasticsearch index templates:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-connect-ecs \
  --data-binary @elasticsearch/templates/kerio-connect-ecs-template.json

curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-flow-template \
  --data-binary @elasticsearch/templates/kerio-flow-template.json
```

If all is well:

- `docker compose up -d` creates and starts `kerio-elasticsearch`, `kerio-logstash`, and `kerio-kibana`;
- `kibana-token-init` runs once and exits successfully;
- each template install command returns JSON that includes `"acknowledged": true`.

If you connect a live Kerio server:

- for real Kerio logs, configure Kerio Connect external syslog to send to `<elk-host>:5514`;
- this quick start does not require a Kerio host because step 4 sends one local synthetic RFC5424 event.

### 4. Verify the result

Verify container state:

```bash
docker compose ps
```

If all is well:

- `kerio-elasticsearch` is `Up` and healthy;
- `kerio-logstash` is `Up`;
- `kerio-kibana` is `Up`;
- `kibana-token-init` shows `Exited (0)` if it is still listed.

Verify Elasticsearch responds:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200 | python3 -m json.tool
```

If all is well:

- the JSON contains `"cluster_name": "kerio-es"`;
- the request succeeds without an authentication error.

Verify the Logstash pipeline is loaded:

```bash
curl -s http://localhost:9600/_node/pipelines?pretty
```

If all is well:

- the output contains `kerio-connect-main`;
- there is no fatal error in the response.

Send one synthetic Kerio-style RFC5424 event to the local UDP input:

```bash
python3 - <<'PY'
import socket

message = (
    "<21>1 2026-04-05T00:00:00Z kerio-connect kerio - - - "
    "Attempt to deliver to unknown recipient <ghost.user.001@example.test>, "
    "from <sender@example.test>, IP address 192.0.2.10\n"
)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(message.encode("utf-8"), ("127.0.0.1", 5514))
sock.close()
PY
```

If all is well:

- the command finishes without output;
- Logstash accepts the packet on `5514/udp`.

Check that Elasticsearch received the parsed event:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD \
  "http://localhost:9200/kerio-connect-*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{"size":1,"sort":[{"@timestamp":{"order":"desc"}}],"query":{"term":{"event.action":"delivery_unknown_recipient"}},"_source":["@timestamp","event.action","event.outcome","email.from.address","email.to.address","kerio.result","network.protocol"]}'
```

If all is well:

- a document is returned from `kerio-connect-*`;
- `event.action` is `delivery_unknown_recipient`;
- `event.outcome` is `failure`;
- `email.from.address` is `sender@example.test`;
- `email.to.address` is `ghost.user.001@example.test`;
- `kerio.result` is `not_delivered`.

### 5. Confirm the outcome

After these steps, you should have:

- a running ELK stack;
- a loaded Logstash pipeline;
- at least one parsed document in `kerio-connect-*`.

You can confirm the index exists with:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cat/indices/kerio-*?v
```

If all is well:

- at least one `kerio-connect-YYYY.MM.DD` index is listed;
- the raw index has a non-zero `docs.count` after the synthetic test event;
- Kibana is reachable at `http://localhost/`.

## Audit Matrix Run

For Kerio audit runs, the repository also includes `scripts/run_audit_matrix.py`.
It reads an existing `identities.json`, tries the available Kerio login paths, and checks the successful authentication entries in `audit.log` over SSH.

Run this when you already have a live Kerio Connect host, SSH access to it, and an `identities.json` from a previous run. It is not required for first-time onboarding; the quick start above intentionally works without a live Kerio host.

The current automated matrix covers:

- `HTTP/WebAdmin` through the Kerio admin JSON-RPC API;
- `HTTP/WebMail` through the Kerio client JSON-RPC API;
- `SMTP` through authenticated submission on `587`;
- `IMAP` through `993`;
- `POP3` through `995`.

`HTTP/KOFF` is listed as a manual-only case because it requires Kerio Outlook Connector / Outlook on the test stand.

Example:

```bash
python3 scripts/run_audit_matrix.py \
  --run-id AUDIT-MATRIX-20260406 \
  --identities-file artifacts/runs/LIVE-PLUS10-20260406-124549/identities.json \
  --output-dir artifacts/runs/AUDIT-MATRIX-20260406/audit
```

Expected artifacts:

- `audit_results.json` with pass / fail / skip details for each protocol;
- `audit_summary.md` with a readable matrix summary.

## Minimal Parser Event

This RFC5424 line is a minimal working example:

```text
<21>1 2026-04-05T00:00:00Z kerio-connect kerio - - - Attempt to deliver to unknown recipient <ghost.user.001@example.test>, from <sender@example.test>, IP address 192.0.2.10
```

## Normalized Result

The expected Elasticsearch document looks like this:

```json
{
  "@timestamp": "2026-04-05T00:00:00.000Z",
  "event": {
    "category": "email",
    "type": "denied",
    "action": "delivery_unknown_recipient",
    "outcome": "failure",
    "reason": "unknown_recipient"
  },
  "process": {
    "name": "kerio"
  },
  "network": {
    "protocol": "smtp"
  },
  "email": {
    "from": {
      "address": "sender@example.test"
    },
    "to": {
      "address": "ghost.user.001@example.test"
    }
  },
  "kerio": {
    "result": "not_delivered"
  }
}
```

## Verification checklist

- [ ] Repository cloned successfully
- [ ] `.env` created with `ELASTIC_PASSWORD`
- [ ] `docker compose up -d` completed successfully
- [ ] Elasticsearch templates installed with `"acknowledged": true`
- [ ] `docker compose ps` shows healthy Elasticsearch and running Logstash/Kibana
- [ ] `curl http://localhost:9600/_node/pipelines?pretty` shows `kerio-connect-main`
- [ ] A synthetic or live Kerio event appears in `kerio-connect-*`
- [ ] Parsed fields match the documented example

## Troubleshooting

### Problem: Elasticsearch exits or keeps restarting

**Symptoms**

- `docker compose ps` shows `kerio-elasticsearch` restarting or exited;
- `docker compose logs elasticsearch` mentions memory pressure or exit code `137`.

**What to check**

- the default heap setting is too large for the Docker memory available on this host.

**How to fix it**

Example fix for a smaller lab host:

```bash
sed -i 's/ES_JAVA_OPTS=-Xms2g -Xmx2g/ES_JAVA_OPTS=-Xms1g -Xmx1g/' docker-compose.yml
docker compose up -d
```

If all is well:

- `kerio-elasticsearch` stays up;
- `curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200` returns JSON instead of a connection error.

### Problem: the pipeline is running, but no events appear in `kerio-connect-*`

**Symptoms**

- `curl http://localhost:9600/_node/pipelines?pretty` shows `kerio-connect-main`;
- the `_search` example returns no results.

**What to check**

- nothing reached `5514`, or the test event was sent before Logstash finished starting.

**How to fix it**

```bash
docker compose logs --tail 50 logstash
curl -s http://localhost:9600/_node/pipelines?pretty | grep kerio-connect-main
```

Then resend the synthetic event from quick start step `4` and run the `_search` command again.

If all is well:

- Logstash is running and listening;
- the next search returns a parsed document.

### Problem: Kibana opens, but links point to the wrong URL or port

**Symptoms**

- Kibana is reachable locally, but generated links or redirects use the wrong public URL.

**What to check**

- `docker-compose.yml` publishes Kibana on host port `80`, while `SERVER_PUBLICBASEURL` may need to match your real external URL.

**How to fix it**

Edit `docker-compose.yml`, then restart Kibana:

```bash
docker compose up -d kibana
```

If all is well:

- Kibana is still reachable;
- the public base URL now matches your environment.

## What This Project Does Not Do

- This repository does not deploy Kerio Connect. It assumes logs come from an existing Kerio source.
- This repository does not replace Kerio or Elastic vendor documentation.
- This repository is not a full production hardening guide for Elastic Stack or Kerio Connect.
- This repository does not include prebuilt dashboards or Grafana content by default.
- This repository is not the tool for anonymizing real customer logs. Use `kerio-syslog-anonymizer` for that.

## What To Know Before Use

- Kerio Connect is proprietary vendor software and is not distributed by this repository.
- Elastic Stack Docker images are third-party software and remain subject to their own licenses and usage terms.
- The Logstash pipeline intentionally uses `pipeline.workers: 1` because mail-flow aggregation relies on the `aggregate` filter.
- Kibana is currently published on host port `80`, so the default local URL is `http://localhost/`.
- `artifacts/runs/` may contain generated passwords, test recipients, and verification output. Keep those files local and out of git.
- `.env` is intentionally ignored because it contains runtime secrets such as `ELASTIC_PASSWORD`, `KERIO_API_USER`, and `KERIO_API_PASSWORD`.

## Roadmap

See [NEXT_STEPS.md](./NEXT_STEPS.md)

## Changelog

See [CHANGELOG.md](./CHANGELOG.md)

Keep `CHANGELOG.md` as the canonical English changelog unless the repository explicitly decides otherwise.

## Handoff

See [HANDOFF.md](./HANDOFF.md)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md)

English is the main language for project documentation and review. Russian README updates are welcome, but they should follow the English README and keep the documented behavior the same.

## GitHub Release Notes

GitHub Release Notes should stay in English and be written for DevOps engineers, sysadmins, and operators.

Focus release notes on what changed for someone running the project:

- changes they can run, observe, validate, or troubleshoot;
- impact on ingestion, parsing, dashboards, scripts, deployment, validation, or generated artifacts;
- exact validation commands, live run IDs, CI status, and expected pass/fail numbers;
- upgrade notes, required operator actions, known limitations, and manual-only steps.

Avoid file-by-file implementation notes unless they change how operators use the project.

## Security

See [SECURITY.md](./SECURITY.md)

## Support

See [SUPPORT.md](./SUPPORT.md)

## License

See [LICENSE](./LICENSE)
