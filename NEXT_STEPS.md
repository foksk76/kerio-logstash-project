# Next Steps

Updated: 2026-04-05 10:17 UTC

## Current State

- Live syslog from the Kerio host into the ELK host is working.
- Final validation passed with `Queue-ID 69d0e1e9-00000003`.
- The stack no longer depends on `testdata/syslog_anonymized.txt`.

## Immediate Steps

1. Optionally update GitHub Actions dependencies to versions that are explicitly ready for the upcoming Node 24 runner switch, because the workflow is green but GitHub still shows deprecation warnings for Node 20-based actions.
2. Decide whether to add a separate release workflow that creates GitHub Releases from tags and optionally publishes changelog notes automatically.
3. Re-run verification on `MAILLOG-KERIO-*` batches after the raw negative-delivery parser fix so historic runs also benefit from the new `kerio.result=not_delivered` field.
4. Flesh out the new `scripts/verify_run.py` scaffold with richer alias-expansion expectations and direct checks for `event.outcome=failure` on raw negative-delivery events.
5. Add regression coverage for both the live Kerio `Recv` format where `Subject` precedes `Msg-Id` and the `Attempt to deliver to unknown recipient` format emitted as `process.name=kerio`.
6. If needed, automate index-template installation so a fresh stack bootstrap has fewer manual steps.
