# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project currently follows a simple manual versioning approach.

## [0.1.0] - 2026-04-01

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
