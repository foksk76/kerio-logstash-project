#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mailtest_common import ensure_dir, load_jsonl, utc_now_iso, write_json

UNPARSED_TAG_RE = re.compile(r"_kerio_[a-z0-9_]+", re.IGNORECASE)
UNKNOWN_RECIPIENT_RE = re.compile(r"unknown recipient", re.IGNORECASE)
EXPANSION_WARNING_RE = re.compile(r"expanded to zero recipients|no local mailbox", re.IGNORECASE)
NONEXISTENT_LOCAL_PART_PREFIX = "ghost.user."
RAW_CORRELATION_WINDOW_SECONDS = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a Kerio logging test run against Kerio, Logstash, and Elasticsearch.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--messages-file", type=Path, required=True)
    parser.add_argument("--elastic-url", required=True)
    parser.add_argument("--elastic-user", default="elastic")
    parser.add_argument("--elastic-password-env", default="ELASTIC_PASSWORD")
    parser.add_argument("--kerio-ssh-host", required=True)
    parser.add_argument("--kerio-container", default="kerio-connect-lab")
    parser.add_argument("--kerio-mail-log", default="/opt/kerio/logs/mail.log")
    parser.add_argument("--logstash-ssh-host", required=True)
    parser.add_argument("--logstash-container", default="kerio-logstash")
    parser.add_argument("--aggregate-wait-seconds", type=int, default=45)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def run_ssh(host: str, command: str) -> str:
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "UserKnownHostsFile=/dev/null",
            f"root@{host}",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return proc.stdout


def fetch_elastic_hits(
    elastic_url: str,
    elastic_user: str,
    elastic_password: str,
    index_pattern: str,
    request_body: dict[str, Any],
) -> list[dict[str, Any]]:
    url = urllib.parse.urljoin(elastic_url.rstrip("/") + "/", f"{index_pattern}/_search")

    token = base64.b64encode(f"{elastic_user}:{elastic_password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        url,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Basic {token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload.get("hits", {}).get("hits", [])


def fetch_elastic_query_string_hits(
    elastic_url: str,
    elastic_user: str,
    elastic_password: str,
    index_pattern: str,
    query_string: str,
) -> list[dict[str, Any]]:
    request_body = {
        "size": 20,
        "sort": [{"@timestamp": "desc"}],
        "query": {"query_string": {"query": query_string}},
    }
    return fetch_elastic_hits(elastic_url, elastic_user, elastic_password, index_pattern, request_body)


def parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


def format_utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def get_message_timestamp(message: dict[str, Any]) -> datetime | None:
    return parse_utc_timestamp(message.get("sent_at")) or parse_utc_timestamp(message.get("planned_at"))


def failure_recipients(message: dict[str, Any]) -> list[str]:
    return sorted(
        recipient
        for recipient in message.get("to", [])
        if recipient.split("@", 1)[0].startswith(NONEXISTENT_LOCAL_PART_PREFIX)
    )


def fetch_raw_failure_hits(
    elastic_url: str,
    elastic_user: str,
    elastic_password: str,
    message: dict[str, Any],
) -> list[dict[str, Any]]:
    recipients = failure_recipients(message)
    timestamp = get_message_timestamp(message)
    if not recipients or timestamp is None:
        return []

    should_terms = []
    for recipient in recipients:
        should_terms.append({"query_string": {"query": f"\"{recipient}\""}})

    request_body = {
        "size": 20,
        "sort": [{"@timestamp": "desc"}],
        "query": {
            "bool": {
                "must": [
                    {
                        "range": {
                            "@timestamp": {
                                "gte": format_utc_timestamp(timestamp - timedelta(seconds=RAW_CORRELATION_WINDOW_SECONDS)),
                                "lte": format_utc_timestamp(timestamp + timedelta(seconds=RAW_CORRELATION_WINDOW_SECONDS)),
                            }
                        }
                    },
                    {"query_string": {"query": f"\"{message['sender']}\""}},
                ],
                "should": should_terms,
                "minimum_should_match": 1,
            }
        },
    }

    return fetch_elastic_hits(
        elastic_url=elastic_url,
        elastic_user=elastic_user,
        elastic_password=elastic_password,
        index_pattern="kerio-connect-*",
        request_body=request_body,
    )


def merge_hits(*hit_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in hit_groups:
        for hit in group:
            hit_id = hit.get("_id")
            if hit_id and hit_id in seen:
                continue
            if hit_id:
                seen.add(hit_id)
            merged.append(hit)
    return merged


def infer_raw_action(hit: dict[str, Any]) -> str | None:
    source = hit.get("_source", {})
    event_action = source.get("event", {}).get("action")
    if event_action:
        return event_action

    candidates = [source.get("message"), source.get("event", {}).get("original")]
    text = " ".join(value for value in candidates if value).lower()
    if UNKNOWN_RECIPIENT_RE.search(text):
        return "delivery_unknown_recipient"
    if EXPANSION_WARNING_RE.search(text):
        return "address_expansion_warning"
    return None


def raw_field_values(raw_hits: list[dict[str, Any]], field_path: tuple[str, ...]) -> list[str]:
    values: set[str] = set()
    for hit in raw_hits:
        value: Any = hit.get("_source", {})
        for key in field_path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if isinstance(value, str) and value:
            values.add(value)
    return sorted(values)


def load_kerio_lines(host: str, container: str, log_path: str, run_id: str) -> list[str]:
    command = f"docker exec {container} sh -lc \"grep -F '{run_id}' {log_path} || true\""
    return [line for line in run_ssh(host, command).splitlines() if line.strip()]


def load_logstash_lines(host: str, container: str, run_id: str) -> list[str]:
    command = f"docker logs {container} 2>&1 | grep -F '{run_id}' || true"
    return [line for line in run_ssh(host, command).splitlines() if line.strip()]


def evaluate_message(
    message: dict[str, Any],
    kerio_lines: list[str],
    logstash_lines: list[str],
    flow_hits: list[dict[str, Any]],
    raw_hits: list[dict[str, Any]],
) -> dict[str, Any]:
    subject = message["subject"]
    message_id = message["message_id"].strip("<>")
    matched_kerio_lines = [line for line in kerio_lines if subject in line or message_id in line]
    matched_logstash_lines = [line for line in logstash_lines if subject in line or message_id in line]
    raw_actions = sorted(
        {
            infer_raw_action(hit)
            for hit in raw_hits
            if infer_raw_action(hit)
        }
    )
    raw_outcomes = raw_field_values(raw_hits, ("event", "outcome"))
    raw_results = raw_field_values(raw_hits, ("kerio", "result"))
    unparsed_tags = sorted({tag for line in matched_logstash_lines for tag in UNPARSED_TAG_RE.findall(line)})

    kerio_recv_seen = any("Recv:" in line for line in matched_kerio_lines)
    kerio_sent_seen = any("Sent:" in line for line in matched_kerio_lines)
    elastic_flow_hit = bool(flow_hits)

    passed = True
    expected = message["expected"]
    send_error_text = str(message.get("send_error") or "").lower()
    raw_failure_confirmed = bool(raw_actions) and "failure" in raw_outcomes
    if "delivery_unknown_recipient" in raw_actions and "not_delivered" not in raw_results:
        raw_failure_confirmed = False

    tolerated_send_error = (
        message.get("send_status") == "error"
        and expected.get("raw_failure")
        and not expected.get("success_flow")
        and raw_failure_confirmed
        and (
            "550" in send_error_text
            or "does not exist" in send_error_text
            or "unknown recipient" in send_error_text
        )
    )

    if message.get("send_status") == "error" and not tolerated_send_error:
        passed = False
    if expected.get("success_flow") and not elastic_flow_hit:
        passed = False
    if expected.get("raw_failure") and not raw_actions:
        passed = False
    if expected.get("raw_failure") and "failure" not in raw_outcomes:
        passed = False
    if "delivery_unknown_recipient" in raw_actions and "not_delivered" not in raw_results:
        passed = False
    if unparsed_tags:
        passed = False

    return {
        "sequence": message["sequence"],
        "scenario": message["scenario"],
        "status": "pass" if passed else "fail",
        "subject": subject,
        "message_id": message["message_id"],
        "kerio_recv_seen": kerio_recv_seen,
        "kerio_sent_seen": kerio_sent_seen,
        "elastic_flow_hit": elastic_flow_hit,
        "elastic_raw_hits": raw_actions,
        "elastic_raw_outcomes": raw_outcomes,
        "elastic_raw_results": raw_results,
        "send_status": message.get("send_status"),
        "send_error": message.get("send_error"),
        "logstash_unparsed_tags": unparsed_tags,
    }


def write_summary(path: Path, results: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    lines = [
        f"# Run Summary: {results['run_id']}",
        "",
        f"- Generated at: {results['generated_at']}",
        f"- Planned messages: {results['summary']['planned_messages']}",
        f"- Passed: {results['summary']['passed']}",
        f"- Failed: {results['summary']['failed']}",
        f"- Unparsed hits: {results['summary']['unparsed_hits']}",
        "",
    ]
    failing = [item for item in results["per_message"] if item["status"] == "fail"]
    if failing:
        lines.append("## Failures")
        lines.append("")
        for item in failing:
            lines.append(f"- seq={item['sequence']} scenario={item['scenario']} subject={item['subject']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    messages = load_jsonl(args.messages_file)
    output_dir = ensure_dir(args.output_dir)

    password = os.environ.get(args.elastic_password_env)
    if not password:
        raise SystemExit(f"Environment variable {args.elastic_password_env} is required")

    if args.aggregate_wait_seconds > 0:
        time.sleep(args.aggregate_wait_seconds)

    kerio_lines = load_kerio_lines(args.kerio_ssh_host, args.kerio_container, args.kerio_mail_log, args.run_id)
    logstash_lines = load_logstash_lines(args.logstash_ssh_host, args.logstash_container, args.run_id)

    per_message: list[dict[str, Any]] = []
    for message in messages:
        subject = message["subject"]
        message_id = message["message_id"].strip("<>")
        query_string = f"\"{subject}\" OR \"{message_id}\""

        try:
            flow_hits = fetch_elastic_query_string_hits(
                elastic_url=args.elastic_url,
                elastic_user=args.elastic_user,
                elastic_password=password,
                index_pattern="kerio-flow-*",
                query_string=query_string,
            )
            raw_hits = fetch_elastic_query_string_hits(
                elastic_url=args.elastic_url,
                elastic_user=args.elastic_user,
                elastic_password=password,
                index_pattern="kerio-connect-*",
                query_string=query_string,
            )
            raw_hits = merge_hits(
                raw_hits,
                fetch_raw_failure_hits(
                    elastic_url=args.elastic_url,
                    elastic_user=args.elastic_user,
                    elastic_password=password,
                    message=message,
                ),
            )
        except urllib.error.URLError as exc:  # pragma: no cover - network behavior
            raise SystemExit(f"Failed to query Elasticsearch: {exc}") from exc

        per_message.append(
            evaluate_message(
                message=message,
                kerio_lines=kerio_lines,
                logstash_lines=logstash_lines,
                flow_hits=flow_hits,
                raw_hits=raw_hits,
            )
        )

    summary = {
        "planned_messages": len(messages),
        "sent_messages": sum(1 for message in messages if message.get("send_status") in {"sent", "dry_run"}),
        "passed": sum(1 for item in per_message if item["status"] == "pass"),
        "failed": sum(1 for item in per_message if item["status"] == "fail"),
        "unparsed_hits": sum(len(item["logstash_unparsed_tags"]) for item in per_message),
    }
    results = {
        "generated_at": utc_now_iso(),
        "run_id": args.run_id,
        "summary": summary,
        "per_message": per_message,
    }

    write_json(output_dir / "results.json", results)
    write_summary(output_dir / "summary.md", results)
    print(json.dumps(summary, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
