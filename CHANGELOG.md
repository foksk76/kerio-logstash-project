# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog and this project currently follows a simple manual versioning approach.

## [Unreleased]

### Fixed

- Fixed the GitHub Actions smoke-test workflow shell snippet in `.github/workflows/ci.yml` by replacing an indented heredoc inside the Elasticsearch polling loop with a stable `python -c` check.
- Fixed the GitHub Actions smoke-test Elasticsearch lookup in `.github/workflows/ci.yml` by replacing a brittle `query_string` search with exact `term` filters on `email.from.address`, `email.to.address`, `event.action`, and `event.outcome`.

## [0.1.2] - 2026-04-05

### Added

- `.github/workflows/ci.yml` with a repository-wide CI pipeline for static checks, Compose validation, Logstash config validation, and a synthetic end-to-end ingestion smoke test.

### Changed

- Replaced the old `pylint-only` GitHub Actions workflow with a broader CI workflow that also validates shell scripts, Elasticsearch templates, README governance links, Docker Compose configuration, and Logstash startup behavior.
- `.gitignore` now also excludes `.env.ci` for local CI-style test runs.
- The synthetic end-to-end smoke test now sends its RFC5424 probe over `5514/tcp` for more deterministic runner behavior while still verifying the same parsing path and indexed fields.
- `README.md` now includes the project-standard GitHub Actions badge at the top of the document, aligned with the rest of the repository family.

## [0.1.1] - 2026-04-05

### Added

- `CONTRIBUTING.md` with contribution expectations for documentation, configuration, and safe sample data.
- `SECURITY.md` with private vulnerability reporting guidance and safe-sharing rules.
- `SUPPORT.md` with issue-reporting expectations and best-effort support guidance.
- `LICENSE` with the Apache 2.0 license text.

### Changed

- Reworked `README.md` to the family-wide documentation standard with a reproducible Quick Start, example input/output, verification checklist, troubleshooting guidance, and governance links.

## [0.1.0] - 2026-04-04

### Added

- `scripts/generate_identities.py` as a scaffold for generating test mailboxes, aliases, and nonexistent recipients.
- `scripts/generate_identities.py` now also writes:
  - `kerio_import_users.csv` as an import-oriented CSV for Kerio users
  - `ui_aliases.csv` as a manual-entry helper for the Kerio aliases web interface
- `scripts/send_mail_batch.py` as a scaffold for constrained-random SMTP mail generation with configurable batch size and send-rate threshold.
- `scripts/verify_run.py` as a scaffold for correlating Kerio logs, Logstash output, and Elasticsearch hits for a test run.
- `artifacts/runs/` as the default ignored location for generated manifests and verification results.

### Changed

- `scripts/generate_identities.py` now generates a unique random 12-character password per mailbox by default, with mixed case, digits, and special characters.
- `kerio_import_users.csv` now uses the same field set and `MailAddress` format as the real Kerio users export sample.
- `kerio_import_users.csv` now follows the sample export defaults for basic users: blank `Description`, `Role=No rights`, zeroed consumption counters, and primary-address-only `MailAddress`.
- Removed generation of the duplicate `users_<domain>_<date>.csv` reference file to keep run artifacts focused on import and verification inputs.
- `kerio_import_users.csv` now includes a `Password` column populated with the generated complex passwords for inline-password import.
- Generated passwords now avoid login, domain, and full-name fragments and use a conservative Kerio-safe special-character set.
- Replaced the raw `provision_aliases.csv` artifact with `ui_aliases.csv`, which uses Kerio UI-friendly alias local-parts and `deliver_to` targets.
- `scripts/verify_run.py` now correlates negative delivery cases by sender, nonexistent recipients, and a short timestamp window, and can infer raw failure types from the event message when `event.action` is absent.
- Release-facing docs now avoid concrete test mailbox examples where a placeholder communicates the same workflow.
- `.gitignore` now excludes Python bytecode caches in addition to local runtime and run-artifact files.
- VS Code helper tasks and search settings are now aligned with the current HTTP-based stack and local generated-artifact workflow.

### Fixed

- Raw Kerio `Attempt to deliver to unknown recipient ...` events now populate `email.from.address`, `email.to.address`, `event.action=delivery_unknown_recipient`, `event.outcome=failure`, and `kerio.result=not_delivered` even when they arrive as `process.name=kerio`.

## [0.1b.4] - 2026-04-04

### Changed

- Removed concrete lab IP addresses from repository-tracked documentation and handoff files.
- Replaced host-specific examples with neutral placeholders such as `<kerio-connect-host>` and `<elk-host>`.

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

- End-to-end live mail flow from a separate Kerio Connect host through Logstash into Elasticsearch `kerio-flow-*`.

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
