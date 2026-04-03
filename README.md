# Kerio Connect Logstash Project

This project parses Kerio Connect syslog, normalizes events to ECS-like fields, aggregates mail flow by Queue-ID, and sends the results to Elasticsearch for analysis in Kibana or Grafana.

Current release: `0.1b.2` (beta).

## Components

- `logstash/pipeline/kerio-connect-main.conf` parses Kerio Connect syslog from a test file, UDP, or TCP input
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
- Docker-based local test environment

## Requirements

- Docker
- Docker Compose plugin
- A valid `.env` file with `ELASTIC_PASSWORD`

## Quick Start

1. Put a test log file at `testdata/syslog_anonymized.txt`.
2. Start the stack:

```bash
docker compose up -d
```

3. Install the Elasticsearch index templates:

```bash
curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-connect-ecs \
  --data-binary @elasticsearch/templates/kerio-connect-ecs-template.json

curl -s -u elastic:$ELASTIC_PASSWORD -H "Content-Type: application/json" \
  -X PUT http://localhost:9200/_index_template/kerio-flow-template \
  --data-binary @elasticsearch/templates/kerio-flow-template.json
```

4. Kibana gets its Elasticsearch service account token automatically during `docker compose up -d`.
5. Open Kibana at `http://localhost:5601`.

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

Stop the stack:

```bash
docker compose down
```

## Notes

- `pipeline.workers` is set to `1` because the mail flow aggregation uses the `aggregate` filter.
- The pipeline writes raw normalized events to `kerio-connect-*` and aggregated flow events to `kerio-flow-*`.
- The Docker deployment auto-generates and reuses a Kibana service account token in a named Docker volume, so no manual `KIBANA_SERVICE_ACCOUNT_TOKEN` is required.
- The current Logstash test workflow intentionally uses `--config.test_and_exit`, so the message about `pipelines.yml` being ignored is expected during validation.

## Validation Status

The project was validated on Ubuntu 24.04 with:

- Docker Engine `28.2.2`
- Docker Compose `2.37.1`
- Logstash `8.19.11`
- Elasticsearch `8.19.11`
- Kibana `8.19.11`
