# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project currently follows a simple manual versioning approach.

## [Unreleased]

No unreleased changes are recorded yet.

## [0.1b.3] - 2026-04-04

### Added

- `HANDOFF.md` to carry the current project state, runtime notes, and latest validation context between chats or hosts.
- `NEXT_STEPS.md` to keep the short operational backlog visible in the repository.

### Changed

- Removed the file-based `testdata/syslog_anonymized.txt` workflow from the main Logstash pipeline.
- Removed the `./testdata:/testdata:ro` mount from `docker-compose.yml`; the stack now expects live syslog on `5514`.
- Updated the README to document the live Kerio Connect syslog workflow and the current Kibana URL on host port `80`.
- Recorded the post-`v0.1b.2` Kibana port change on `main` so the changelog matches the running stack.

### Fixed

- Mail parsing now accepts live Kerio RFC5424 events where `process.name` is `kerio` instead of `mail`.
- `Recv` parsing now matches the live Kerio format where `Subject` appears before `Msg-Id` and `SSL` may be omitted.

### Validated

- End-to-end live mail flow from Kerio Connect `10.4.29.71` through Logstash `10.4.29.70` into Elasticsearch `kerio-flow-*`.

## [0.1b.2] - 2026-04-03

### Added

- Automatic Kibana service-account token bootstrap through `kibana-token-init`.
- Runtime helper scripts for Kibana token generation and startup.
- Named Docker volume for reusable Kibana token storage.

### Changed

- Updated the README to reflect automatic Kibana token provisioning.

## [0.1b.1] - 2026-04-02

### Changed

- Switched local Elasticsearch and Kibana stack wiring from HTTPS to HTTP for the internal Docker network.
- Updated README examples and healthchecks to use the local HTTP endpoints.
- Expanded and refined the main Logstash pipeline for Kerio event parsing and normalization.

## [0.1b.0] - 2026-04-01

First beta release.

### Added

- Initial Docker-based Kerio Connect parsing stack with Elasticsearch, Kibana, and Logstash
- Kerio Connect parsing pipeline for audit, security, warn, operations, and mail logs
- Elasticsearch index templates for normalized events and aggregated mail flow
- English project README
- Initial changelog

### Changed

- Fixed `logstash/config/logstash.yml` so it contains actual Logstash runtime settings
- Set `pipeline.workers: 1` for safe `aggregate` filter behavior
- Updated Elasticsearch output settings to current Logstash option names
- Removed deprecated Compose file version field
- Removed obsolete local VS Code launch shortcut

### Validated

- `docker compose --env-file .env config`
- `logstash --config.test_and_exit` in the Docker test environment on Ubuntu 24.04
