# Kerio Connect Logstash Project

This project parses Kerio Connect syslog, normalizes events to ECS-like fields, aggregates mail flow by Queue-ID, and sends the results to Elasticsearch for analysis in Kibana or Grafana.

Latest tagged release: `v0.1b.4` (beta).

## Components

- `logstash/pipeline/kerio-connect-main.conf` parses Kerio Connect syslog from UDP or TCP input on port `5514`
- `logstash/config/logstash.yml` contains Logstash runtime settings
- `logstash/config/pipelines.yml` registers the main pipeline
- `elasticsearch/templates/kerio-connect-ecs-template.json` defines mappings for raw normalized events
- `elasticsearch/templates/kerio-flow-template.json` defines mappings for aggregated mail flow events
- `docker-compose.yml` starts Elasticsearch, Kibana, and Logstash together

## Features

- RFC5424 syslog envelope parsing
- Kerio Connect audit, security, warn, operations, and mail log parsing
- ECS-style field normalization for users, hosts, IPs, email metadata, and event categories
- Mail flow aggregation by `Queue-ID`
- Separate Elasticsearch indices for raw events and aggregated flow events
- Docker-based live syslog receiver for Kerio Connect

## Requirements

- Docker
- Docker Compose plugin
- A valid `.env` file with `ELASTIC_PASSWORD`
- A Kerio Connect host configured to send syslog to this stack on `5514/udp` or `5514/tcp`

## Quick Start

1. Start the stack:

```bash
docker compose up -d
```

2. Install the Elasticsearch index templates:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-connect-ecs \
  --data-binary @elasticsearch/templates/kerio-connect-ecs-template.json

curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-flow-template \
  --data-binary @elasticsearch/templates/kerio-flow-template.json
```

3. In Kerio Connect, enable external syslog logging and point it to this host on port `5514`.

HomeLab example:

- Kerio Connect host: `<kerio-connect-host>`
- ELK / Logstash host: `<elk-host>`
- Syslog target: `<elk-host>:5514`

4. Kibana gets its Elasticsearch service account token automatically during `docker compose up -d`.
5. Open Kibana at `http://localhost/`.

## Useful Commands

Validate the Logstash pipeline:

```bash
docker compose --env-file .env run --no-deps --rm logstash \
  /usr/share/logstash/bin/logstash \
  --path.settings /usr/share/logstash/config \
  --config.test_and_exit \
  -f /usr/share/logstash/pipeline/kerio-connect-main.conf
```

View Logstash logs:

```bash
docker compose logs -f logstash
```

Inspect the pipeline status:

```bash
curl -s http://localhost:9600/_node/pipelines?pretty
```

Find the latest aggregated mail flows:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD \
  "http://localhost:9200/kerio-flow-*/_search?pretty" \
  -H "Content-Type: application/json" \
  -d '{"size":5,"sort":[{"@timestamp":"desc"}]}'
```

Stop the stack:

```bash
docker compose down
```

## Notes

- `pipeline.workers` is set to `1` because the mail flow aggregation uses the `aggregate` filter.
- The pipeline writes raw normalized events to `kerio-connect-*` and aggregated flow events to `kerio-flow-*`.
- The Docker deployment auto-generates and reuses a Kibana service account token in a named Docker volume, so no manual `KIBANA_SERVICE_ACCOUNT_TOKEN` is required.
- Kibana is currently published on host port `80`, so the default browser URL is `http://localhost/`.
- The pipeline is tuned for live Kerio RFC5424 syslog and no longer reads a local `testdata/syslog_anonymized.txt` file.
- The current Logstash test workflow intentionally uses `--config.test_and_exit`, so the message about `pipelines.yml` being ignored is expected during validation.

## Validation Status

The project was validated on Ubuntu 24.04 with:

- Docker Engine `28.2.2`
- Docker Compose `2.37.1`
- Logstash `8.19.11`
- Elasticsearch `8.19.11`
- Kibana `8.19.11`
- Live Kerio Connect syslog from a separate Kerio host into Logstash on the ELK host
