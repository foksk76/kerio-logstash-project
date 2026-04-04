# Next Steps

Updated: 2026-04-04 10:13 UTC

## Current State

- Live syslog from the Kerio host into the ELK host is working.
- Final validation passed with `Queue-ID 69d0e1e9-00000003`.
- The stack no longer depends on `testdata/syslog_anonymized.txt`.

## Immediate Steps

1. Monitor `docker logs kerio-logstash` for `_kerio_mail_unparsed_v2`, `_kerio_security_unparsed`, `_kerio_warn_unparsed`, and `_kerio_operations_unparsed` tags when new live events appear.
2. Decide whether to align Kibana `SERVER_PUBLICBASEURL` with the current host port `80` if absolute links or shared URLs matter.
3. Add regression coverage for the live Kerio `Recv` format where `Subject` precedes `Msg-Id` and `SSL` is absent.
4. If needed, automate index-template installation so a fresh stack bootstrap has fewer manual steps.
