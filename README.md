# Kerio Connect Logstash Project

Parsing, normalization, enrichment, and mail-flow correlation for Kerio Connect syslog into Elasticsearch.

[![CI](https://github.com/foksk76/kerio-logstash-project/actions/workflows/ci.yml/badge.svg)](https://github.com/foksk76/kerio-logstash-project/actions/workflows/ci.yml)

## Why this repository exists

Kerio Connect can emit useful operational, security, and mail-flow events over syslog, but those logs are not ready for dashboards or repeatable analysis as-is.

This repository exists to:

- receive live Kerio Connect RFC5424 syslog;
- parse Kerio-specific log formats into ECS-like fields;
- enrich and normalize events for Elasticsearch queries and Kibana exploration;
- aggregate related mail events by `Queue-ID` so message flow is easier to inspect;
- provide a reproducible local ELK stack for parser development and validation.

The expected outcome is simple: start the stack, send Kerio syslog to `5514`, and get searchable raw events in `kerio-connect-*` plus aggregated mail-flow events in `kerio-flow-*`.

## Project family

This repository is part of the **Kerio Connect Monitoring & Logging** project family:

1. [kerio-connect](https://github.com/foksk76/kerio-connect) — reproducible Kerio Connect lab environment
2. [kerio-logstash-project](https://github.com/foksk76/kerio-logstash-project) — parsing, normalization, and enrichment pipeline for Kerio syslog
3. [kerio-syslog-anonymizer](https://github.com/foksk76/kerio-syslog-anonymizer) — deterministic anonymization of real log data for safe public use

## Where this repository fits

This repository is the parsing and storage layer in the family flow:

`Kerio Connect -> Syslog (RFC5424) -> Logstash -> Elasticsearch -> Kibana / Grafana`

If you need:

- a reproducible Kerio Connect lab source, use `kerio-connect`;
- safe public sample logs, use `kerio-syslog-anonymizer`;
- live parsing, normalization, and validation of Kerio syslog, use this repository.

## Main use cases

- Receive live Kerio Connect syslog over `5514/udp` or `5514/tcp`.
- Normalize audit, security, warn, operations, and mail logs into ECS-like fields.
- Aggregate `Recv` / `Sent` mail events into message-flow documents by `Queue-ID`.
- Validate parser changes locally with synthetic RFC5424 test events.
- Run batch mail-log tests with the included helper scripts.

## Audience

- beginner DevOps engineers who need a reproducible ELK-based parser stack;
- sysadmins operating Kerio Connect and wanting structured log search;
- homelab users testing Kerio logging end to end;
- observability and SecOps practitioners building queries or dashboards on top of Kerio events;
- contributors extending the Logstash parser.

## Architecture / Flow

1. Kerio Connect sends RFC5424 syslog to Logstash on port `5514`.
2. Logstash parses the syslog envelope and then applies Kerio-specific parsing rules from `logstash/pipeline/kerio-connect-main.conf`.
3. Raw normalized events are stored in `kerio-connect-*`.
4. Mail events with a `Queue-ID` are aggregated into message-flow documents and stored in `kerio-flow-*`.
5. Elasticsearch makes both raw and aggregated views available to Kibana or Grafana.
6. Optional helper scripts in `scripts/` can generate test identities, send synthetic mail batches, and verify the indexed results.

## Requirements

### Software

- Debian, Ubuntu, or another Linux environment with Docker support
- Docker Engine
- Docker Compose plugin
- `curl`
- `python3` for the local verification example and helper scripts
- A Kerio Connect host if you want live vendor logs instead of synthetic test input

### Hardware

- 2 vCPU minimum
- 6 GB RAM available to Docker is the practical baseline for the shipped defaults
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

```text
.
├── README.md
├── CHANGELOG.md
├── HANDOFF.md
├── NEXT_STEPS.md
├── docker-compose.yml
├── docker/
│   └── kibana/
│       ├── generate-service-token.sh
│       └── start-with-service-token.sh
├── elasticsearch/
│   └── templates/
│       ├── kerio-connect-ecs-template.json
│       └── kerio-flow-template.json
├── logstash/
│   ├── config/
│   │   ├── logstash.yml
│   │   └── pipelines.yml
│   └── pipeline/
│       └── kerio-connect-main.conf
├── scripts/
│   ├── generate_identities.py
│   ├── mailtest_common.py
│   ├── send_mail_batch.py
│   └── verify_run.py
└── artifacts/
    ├── .gitignore
    └── runs/
```

## Quick Start

This Quick Start verifies four things:

- the ELK stack starts;
- the Logstash pipeline is loaded;
- the syslog input accepts traffic;
- a parsed Kerio event becomes visible in Elasticsearch.

### 1. Clone the repository

```bash
git clone https://github.com/foksk76/kerio-logstash-project.git
cd kerio-logstash-project
```

Expected result:

- the current directory is the repository root;
- files such as `docker-compose.yml` and `README.md` are present.

### 2. Prepare the environment

Create `.env` with the Elasticsearch password that the stack will use:

```bash
cat > .env <<'EOF'
ELASTIC_PASSWORD=ChangeMe-2026!
EOF
```

What you must edit:

- replace `ChangeMe-2026!` if you do not want to keep the example password;
- keep the variable name exactly `ELASTIC_PASSWORD`.

What is mandatory:

- `.env` must exist before `docker compose up -d`;
- the same password must be used for all `curl -u elastic:$ELASTIC_PASSWORD ...` commands below.

What to review before first start:

- `docker-compose.yml` currently sets `ES_JAVA_OPTS=-Xms2g -Xmx2g` and `LS_JAVA_OPTS=-Xms1g -Xmx1g`;
- if your Docker host cannot spare that memory, lower those values in `docker-compose.yml` before starting the stack.

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

What success looks like:

- `docker compose up -d` creates and starts `kerio-elasticsearch`, `kerio-logstash`, and `kerio-kibana`;
- `kibana-token-init` runs once and exits successfully;
- each template install command returns JSON that includes `"acknowledged": true`.

Notes for live use:

- for real Kerio logs, configure Kerio Connect external syslog to send to `<elk-host>:5514`;
- this Quick Start does not require a live Kerio host because it injects one synthetic RFC5424 event locally in step 4.

### 4. Verify the result

Verify container state:

```bash
docker compose ps
```

Expected result:

- `kerio-elasticsearch` is `Up` and healthy;
- `kerio-logstash` is `Up`;
- `kerio-kibana` is `Up`;
- `kibana-token-init` shows `Exited (0)` if it is still listed.

Verify Elasticsearch responds:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200 | python3 -m json.tool
```

Expected result:

- the JSON contains `"cluster_name": "kerio-es"`;
- the request succeeds without an authentication error.

Verify the Logstash pipeline is loaded:

```bash
curl -s http://localhost:9600/_node/pipelines?pretty
```

Expected result:

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

Expected result:

- the command finishes without output;
- Logstash accepts the packet on `5514/udp`.

Verify parsed output and Elasticsearch index visibility:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD \
  "http://localhost:9200/kerio-connect-*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{"size":1,"sort":[{"@timestamp":{"order":"desc"}}],"query":{"term":{"event.action.keyword":"delivery_unknown_recipient"}},"_source":["@timestamp","event.action","event.outcome","email.from.address","email.to.address","kerio.result","network.protocol"]}'
```

Expected result:

- a document is returned from `kerio-connect-*`;
- `event.action` is `delivery_unknown_recipient`;
- `event.outcome` is `failure`;
- `email.from.address` is `sender@example.test`;
- `email.to.address` is `ghost.user.001@example.test`;
- `kerio.result` is `not_delivered`.

### 5. Example outcome

After the steps above, you should have:

- a running ELK stack;
- a loaded Logstash pipeline;
- at least one parsed document in `kerio-connect-*`.

You can confirm the index exists with:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cat/indices/kerio-*?v
```

Expected result:

- at least one `kerio-connect-YYYY.MM.DD` index is listed;
- the raw index has a non-zero `docs.count` after the synthetic test event;
- Kibana is reachable at `http://localhost/`.

## Example input

The following RFC5424 line is a valid minimal example for the current parser:

```text
<21>1 2026-04-05T00:00:00Z kerio-connect kerio - - - Attempt to deliver to unknown recipient <ghost.user.001@example.test>, from <sender@example.test>, IP address 192.0.2.10
```

## Example output

One expected normalized raw event looks like this:

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

**Cause**

- the shipped heap setting is too large for the available Docker memory.

**Solution**

Example fix for a smaller lab host:

```bash
sed -i 's/ES_JAVA_OPTS=-Xms2g -Xmx2g/ES_JAVA_OPTS=-Xms1g -Xmx1g/' docker-compose.yml
docker compose up -d
```

Expected result:

- `kerio-elasticsearch` stays up;
- `curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200` returns JSON instead of a connection error.

### Problem: the pipeline is up but no events appear in `kerio-connect-*`

**Symptoms**

- `curl http://localhost:9600/_node/pipelines?pretty` shows `kerio-connect-main`;
- the `_search` example returns zero hits.

**Cause**

- no input reached `5514`, or the test event was sent before Logstash finished starting.

**Solution**

```bash
docker compose logs --tail 50 logstash
curl -s http://localhost:9600/_node/pipelines?pretty | grep kerio-connect-main
```

Then resend the synthetic packet from Quick Start step `4` and rerun the `_search` command.

Expected result:

- Logstash is running and listening;
- the next search returns a parsed document.

### Problem: Kibana opens on the wrong URL or shared links point to the wrong port

**Symptoms**

- Kibana is reachable locally, but generated links or redirects use the wrong public URL.

**Cause**

- `docker-compose.yml` currently publishes Kibana on host port `80`, while `SERVER_PUBLICBASEURL` may need to match your real external URL.

**Solution**

Edit `docker-compose.yml`, then restart Kibana:

```bash
docker compose up -d kibana
```

Expected result:

- Kibana is still reachable;
- the public base URL now matches your environment.

## Limitations / Non-goals

- This repository is not a Kerio Connect deployment project; it assumes logs come from an existing Kerio source.
- This repository is not a replacement for vendor documentation.
- This repository is not a full production hardening guide for Elastic Stack or Kerio Connect.
- This repository does not ship prebuilt dashboards or Grafana content by default.
- This repository is not the anonymization tool for publishing real customer logs; use `kerio-syslog-anonymizer` for that.

## Notes

- Kerio Connect itself is proprietary vendor software and is not distributed by this repository.
- Elastic Stack Docker images are third-party software and remain subject to their own licensing and usage terms.
- The Logstash pipeline intentionally uses `pipeline.workers: 1` because mail-flow aggregation relies on the `aggregate` filter.
- Kibana is currently published on host port `80`, so the default local URL is `http://localhost/`.
- `artifacts/runs/` may contain generated passwords, test recipients, and verification output. Keep those files local and out of git.
- `.env` is intentionally ignored because it contains runtime secrets such as `ELASTIC_PASSWORD`.

## Roadmap

See [NEXT_STEPS.md](./NEXT_STEPS.md)

## Changelog

See [CHANGELOG.md](./CHANGELOG.md)

## Handoff

See [HANDOFF.md](./HANDOFF.md)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md)

## Security

See [SECURITY.md](./SECURITY.md)

## Support

See [SUPPORT.md](./SUPPORT.md)

## License

See [LICENSE](./LICENSE)
