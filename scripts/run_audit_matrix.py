#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import imaplib
import json
import poplib
import shlex
import smtplib
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.kerio_api import DEFAULT_KERIO_API_URL, KerioAdminClient, env_or_dotenv
from scripts.mailtest_common import ensure_dir, load_json, utc_now_iso, utc_now_precise_iso, write_json

DEFAULT_WEBMAIL_API_URL = "https://kerio.lo/webmail/api/jsonrpc/"
DEFAULT_ELASTIC_URL = "http://elastic.lo:9200"
DEFAULT_AUDIT_SSH_TARGET = "root@kerio.lo"
DEFAULT_AUDIT_CONTAINER = "kerio-connect-lab"
DEFAULT_AUDIT_LOG_PATH = "/opt/kerio/logs/audit.log"
DEFAULT_VERIFY_TIMEOUT = 15
DEFAULT_ELASTIC_VERIFY_TIMEOUT = 45
DEFAULT_TAIL_LINES = 400
DEFAULT_ELASTIC_LOOKBACK = "now-30m"
DEFAULT_ELASTIC_CASE_LOOKBACK_SECONDS = 15

AUDIT_LINE_MARKER = "authenticated  from IP address"

CASE_SPECS = [
    {
        "case_id": "http_webadmin",
        "protocol": "HTTP/WebAdmin",
        "transport": "admin_api_https_4040",
        "mode": "admin_api",
    },
    {
        "case_id": "http_webmail",
        "protocol": "HTTP/WebMail",
        "transport": "webmail_api_https_443",
        "mode": "webmail_api",
    },
    {
        "case_id": "smtp",
        "protocol": "SMTP",
        "transport": "submission_starttls_587",
        "mode": "smtp_submission",
        "port": 587,
    },
    {
        "case_id": "imap",
        "protocol": "IMAP",
        "transport": "imaps_993",
        "mode": "imaps",
        "port": 993,
    },
    {
        "case_id": "pop3",
        "protocol": "POP3",
        "transport": "pop3s_995",
        "mode": "pop3s",
        "port": 995,
    },
]

MANUAL_CASES = [
    {
        "case_id": "http_koff",
        "protocol": "HTTP/KOFF",
        "transport": "outlook_connector_http",
        "status": "manual_required",
        "reason": "Kerio Outlook Connector / Outlook session is not available on this stand.",
    }
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Exercise Kerio Connect audit authentication events from identities.json.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--identities-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--kerio-host", default="kerio.lo")
    parser.add_argument("--kerio-admin-api-url", default=DEFAULT_KERIO_API_URL)
    parser.add_argument("--kerio-webmail-api-url", default=DEFAULT_WEBMAIL_API_URL)
    parser.add_argument("--kerio-api-user-env", default="KERIO_API_USER")
    parser.add_argument("--kerio-api-password-env", default="KERIO_API_PASSWORD")
    parser.add_argument("--kerio-env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--kerio-verify-tls", action="store_true")
    parser.add_argument("--audit-ssh-target", default=DEFAULT_AUDIT_SSH_TARGET)
    parser.add_argument("--audit-container", default=DEFAULT_AUDIT_CONTAINER)
    parser.add_argument("--audit-log-path", default=DEFAULT_AUDIT_LOG_PATH)
    parser.add_argument("--tail-lines", type=int, default=DEFAULT_TAIL_LINES)
    parser.add_argument("--verify-timeout-seconds", type=int, default=DEFAULT_VERIFY_TIMEOUT)
    parser.add_argument("--elastic-verify-timeout-seconds", type=int, default=DEFAULT_ELASTIC_VERIFY_TIMEOUT)
    parser.add_argument("--elastic-url", default=DEFAULT_ELASTIC_URL)
    parser.add_argument("--elastic-user", default="elastic")
    parser.add_argument("--elastic-password-env", default="ELASTIC_PASSWORD")
    parser.add_argument("--elastic-lookback", default=DEFAULT_ELASTIC_LOOKBACK)
    parser.add_argument("--elastic-case-lookback-seconds", type=int, default=DEFAULT_ELASTIC_CASE_LOOKBACK_SECONDS)
    return parser


def read_audit_tail(args: argparse.Namespace) -> list[str]:
    remote_tail = (
        f"docker exec {shlex.quote(args.audit_container)} "
        f"sh -lc {shlex.quote(f'tail -n {args.tail_lines} {shlex.quote(args.audit_log_path)}')}"
    )
    remote_cmd = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        args.audit_ssh_target,
        remote_tail,
    ]
    completed = subprocess.run(remote_cmd, check=True, capture_output=True, text=True)
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def parse_audit_line(line: str) -> dict[str, str] | None:
    if AUDIT_LINE_MARKER not in line or ": User " not in line:
        return None

    try:
        timestamp_end = line.index("]")
        timestamp = line[1:timestamp_end]
        remainder = line[timestamp_end + 2 :]
        protocol, remainder = remainder.split(": User ", 1)
        user, remainder = remainder.split(" authenticated  from IP address ", 1)
    except ValueError:
        return None

    ip, _, user_agent = remainder.partition("; ")
    payload = {
        "timestamp": timestamp,
        "protocol": protocol.strip(),
        "user": user.strip(),
        "ip": ip.strip(),
        "line": line,
    }
    if user_agent:
        payload["user_agent"] = user_agent.strip()
    return payload


def recent_observed_protocols(lines: list[str]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    samples: dict[str, str] = {}
    for line in lines:
        parsed = parse_audit_line(line)
        if parsed is None:
            continue
        protocol = parsed["protocol"]
        counts[protocol] = counts.get(protocol, 0) + 1
        samples.setdefault(protocol, parsed["line"])
    return [
        {"protocol": protocol, "count": counts[protocol], "sample": samples[protocol]}
        for protocol in sorted(counts)
    ]


def probe_tcp(host: str, port: int, timeout: int = 10) -> dict[str, Any]:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return {"reachable": True, "message": f"tcp/{port} reachable"}
    except OSError as exc:
        return {"reachable": False, "message": str(exc)}


def json_rpc_call(
    *,
    url: str,
    method: str,
    params: dict[str, Any],
    verify_tls: bool,
    token: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    if token:
        payload["token"] = token
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json-rpc; charset=UTF-8",
            "Accept": "application/json-rpc",
        },
        method="POST",
    )
    context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
    with urllib.request.urlopen(request, context=context, timeout=30) as response:
        body = json.loads(response.read().decode("utf-8"))
    if "error" in body:
        raise RuntimeError(body["error"].get("message", json.dumps(body["error"], ensure_ascii=True)))
    return body.get("result", {})


def login_webmail_api(
    *,
    url: str,
    username: str,
    password: str,
    run_id: str,
    verify_tls: bool,
) -> dict[str, Any]:
    result = json_rpc_call(
        url=url,
        method="Session.login",
        params={
            "userName": username,
            "password": password,
            "application": {
                "name": f"kerio-logstash audit matrix {run_id} webmail",
                "vendor": "OpenAI",
                "version": "1.0",
            },
        },
        verify_tls=verify_tls,
    )
    token = result.get("token")
    return {"token_present": bool(token)}


def exercise_admin_api(
    args: argparse.Namespace,
    admin_username: str,
    admin_password: str,
) -> dict[str, Any]:
    with KerioAdminClient(
        api_url=args.kerio_admin_api_url,
        username=admin_username,
        password=admin_password,
        verify_tls=args.kerio_verify_tls,
        application_name=f"kerio-logstash audit matrix {args.run_id} admin",
        application_vendor="OpenAI",
        application_version="1.0",
    ) as client:
        domain = client.get_domain(load_json(args.identities_file)["domain"])
        return {"domain_id": domain["id"], "domain_name": domain["name"]}


def exercise_case(case: dict[str, Any], args: argparse.Namespace, actor: dict[str, str] | None) -> dict[str, Any]:
    mode = case["mode"]
    if mode == "admin_api":
        admin_username = env_or_dotenv(args.kerio_api_user_env, args.kerio_env_file)
        admin_password = env_or_dotenv(args.kerio_api_password_env, args.kerio_env_file)
        if not admin_username or not admin_password:
            raise RuntimeError("Kerio admin API credentials are required for HTTP/WebAdmin audit exercise")
        return exercise_admin_api(args, admin_username, admin_password)
    if actor is None:
        raise RuntimeError(f"Identity actor is required for case {case['case_id']}")

    if mode == "webmail_api":
        return login_webmail_api(
            url=args.kerio_webmail_api_url,
            username=actor["address"],
            password=actor["password"],
            run_id=args.run_id,
            verify_tls=args.kerio_verify_tls,
        )
    if mode == "smtp_submission":
        with smtplib.SMTP(args.kerio_host, case["port"], timeout=30) as smtp:
            smtp.ehlo()
            if smtp.has_extn("starttls"):
                smtp.starttls(context=ssl.create_default_context() if args.kerio_verify_tls else ssl._create_unverified_context())
                smtp.ehlo()
            smtp.login(actor["address"], actor["password"])
        return {"port": case["port"]}
    if mode == "imaps":
        with imaplib.IMAP4_SSL(
            args.kerio_host,
            case["port"],
            ssl_context=ssl.create_default_context() if args.kerio_verify_tls else ssl._create_unverified_context(),
        ) as client:
            client.login(actor["address"], actor["password"])
            client.logout()
        return {"port": case["port"]}
    if mode == "pop3s":
        client = poplib.POP3_SSL(
            args.kerio_host,
            case["port"],
            context=ssl.create_default_context() if args.kerio_verify_tls else ssl._create_unverified_context(),
            timeout=30,
        )
        try:
            client.user(actor["address"])
            client.pass_(actor["password"])
        finally:
            client.quit()
        return {"port": case["port"]}

    raise ValueError(f"Unsupported case mode: {mode}")


def match_new_audit_line(
    *,
    before_lines: list[str],
    after_lines: list[str],
    protocol: str,
    expected_user: str,
) -> dict[str, str] | None:
    baseline = set(before_lines)
    for line in reversed(after_lines):
        parsed = parse_audit_line(line)
        if parsed is None:
            continue
        if line in baseline:
            continue
        if parsed["protocol"] != protocol:
            continue
        if parsed["user"] != expected_user:
            continue
        return parsed
    return None


def wait_for_audit_match(
    *,
    args: argparse.Namespace,
    before_lines: list[str],
    protocol: str,
    expected_user: str,
) -> dict[str, Any]:
    deadline = time.time() + args.verify_timeout_seconds
    while time.time() < deadline:
        after_lines = read_audit_tail(args)
        parsed = match_new_audit_line(
            before_lines=before_lines,
            after_lines=after_lines,
            protocol=protocol,
            expected_user=expected_user,
        )
        if parsed is not None:
            return {"found": True, "match": parsed}
        time.sleep(1)
    return {"found": False, "match": None}


def shift_iso_timestamp(value: str, *, seconds: int) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    shifted = parsed + timedelta(seconds=seconds)
    return shifted.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def elastic_query(
    *,
    elastic_url: str,
    username: str,
    password: str,
    actor_emails: list[str],
    lookback: str,
) -> dict[str, Any]:
    query = {
        "size": 50,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"event.action": "user_authenticated"}},
                    {"terms": {"user.email": actor_emails}},
                    {"range": {"@timestamp": {"gte": lookback}}},
                ]
            }
        },
        "_source": [
            "@timestamp",
            "process.name",
            "event.action",
            "event.outcome",
            "network.protocol",
            "kerio.protocol",
            "user.email",
            "source.ip",
            "message",
        ],
    }
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"{elastic_url.rstrip('/')}/kerio-connect-*/_search",
        data=json.dumps(query).encode("utf-8"),
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    hits = payload.get("hits", {}).get("hits", [])
    return {"hit_count": len(hits), "hits": hits}


def elastic_query_case(
    *,
    elastic_url: str,
    username: str,
    password: str,
    protocol: str,
    actor_email: str,
    started_at: str,
    lookback_seconds: int,
) -> dict[str, Any]:
    query = {
        "size": 5,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {
            "bool": {
                "filter": [
                    {"term": {"event.action": "user_authenticated"}},
                    {"term": {"user.email": actor_email}},
                    {
                        "bool": {
                            "should": [
                                {"term": {"kerio.protocol": protocol}},
                                {"term": {"kerio.protocol_raw": protocol}},
                            ],
                            "minimum_should_match": 1,
                        }
                    },
                    {"range": {"@timestamp": {"gte": shift_iso_timestamp(started_at, seconds=-lookback_seconds)}}},
                ]
            }
        },
        "_source": [
            "@timestamp",
            "event.action",
            "event.outcome",
            "network.protocol",
            "kerio.log_type",
            "kerio.protocol",
            "kerio.protocol_raw",
            "user.email",
            "source.ip",
            "message",
            "tags",
        ],
    }
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    request = urllib.request.Request(
        f"{elastic_url.rstrip('/')}/kerio-connect-*/_search",
        data=json.dumps(query).encode("utf-8"),
        headers={
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    hits = payload.get("hits", {}).get("hits", [])
    return {"hit_count": len(hits), "hits": hits}


def wait_for_elastic_case_match(
    *,
    args: argparse.Namespace,
    elastic_password: str,
    protocol: str,
    actor_email: str,
    started_at: str,
) -> dict[str, Any]:
    deadline = time.time() + args.elastic_verify_timeout_seconds
    last_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        payload = elastic_query_case(
            elastic_url=args.elastic_url,
            username=args.elastic_user,
            password=elastic_password,
            protocol=protocol,
            actor_email=actor_email,
            started_at=started_at,
            lookback_seconds=args.elastic_case_lookback_seconds,
        )
        last_payload = payload
        if payload["hit_count"] > 0:
            return {"found": True, "payload": payload}
        time.sleep(1)
    return {"found": False, "payload": last_payload or {"hit_count": 0, "hits": []}}


def build_markdown_report(result: dict[str, Any]) -> str:
    lines = [
        f"# Kerio Audit Matrix Run `{result['run_id']}`",
        "",
        f"- Generated at: `{result['generated_at']}`",
        f"- Identities file: `{result['identities_file']}`",
        f"- Kerio host: `{result['kerio_host']}`",
        f"- Audit verification: `Kerio audit.log over SSH`",
        "",
        "## Recent Observed Audit Protocols",
        "",
    ]

    observed = result["recent_observed_protocols"]
    if observed:
        for row in observed:
            lines.append(f"- `{row['protocol']}`: {row['count']} recent entries")
    else:
        lines.append("- No recent audit entries were found in the sampled tail.")

    lines.extend(["", "## Automated Cases", ""])
    for case in result["cases"]:
        actor = case.get("actor_email") or "n/a"
        lines.append(
            f"- `{case['case_id']}` / `{case['protocol']}` / actor `{actor}` -> `{case['status']}`"
        )
        if case.get("matched_line"):
            lines.append(f"  matched: `{case['matched_line']}`")
        if case.get("elastic_hit"):
            lines.append(
                f"  elastic: `{case['elastic_hit']['@timestamp']}` / `{case['elastic_hit']['message']}`"
            )
        elif case.get("reason"):
            lines.append(f"  reason: `{case['reason']}`")

    lines.extend(["", "## Manual Cases", ""])
    for case in result["manual_cases"]:
        lines.append(f"- `{case['case_id']}` / `{case['protocol']}` -> `{case['status']}`")
        lines.append(f"  reason: `{case['reason']}`")

    elastic = result.get("elastic_check")
    if elastic:
        lines.extend(["", "## Elasticsearch", ""])
        if elastic.get("error"):
            lines.append(f"- check failed: `{elastic['error']}`")
        else:
            lines.append(f"- cases confirmed in Elasticsearch: `{elastic['confirmed_cases']}` / `{elastic['checked_cases']}`")
            for row in elastic.get("case_results", []):
                lines.append(
                    f"  - `{row['case_id']}` / `{row['protocol']}` / `{row['actor_email']}` -> `{row['hit_count']}` hit(s)"
                )

    return "\n".join(lines) + "\n"


def main() -> int:
    args = build_parser().parse_args()
    identities = load_json(args.identities_file)
    users = identities["users"]
    if len(users) < 4:
        raise SystemExit("identities.json must contain at least four users to cover WebMail/SMTP/IMAP/POP3")
    elastic_password = env_or_dotenv(args.elastic_password_env, args.kerio_env_file)

    recent_before = read_audit_tail(args)
    results: list[dict[str, Any]] = []

    non_admin_users = iter(users)
    actor_map = {
        "http_webmail": next(non_admin_users),
        "smtp": next(non_admin_users),
        "imap": next(non_admin_users),
        "pop3": next(non_admin_users),
    }

    for case in CASE_SPECS:
        actor = actor_map.get(case["case_id"])
        expected_user = env_or_dotenv(args.kerio_api_user_env, args.kerio_env_file) if case["case_id"] == "http_webadmin" else actor["address"]
        before_lines = read_audit_tail(args)
        result: dict[str, Any] = {
            "case_id": case["case_id"],
            "protocol": case["protocol"],
            "transport": case["transport"],
            "mode": case["mode"],
            "actor_email": expected_user,
            "status": "planned",
            "started_at": utc_now_precise_iso(),
        }

        if "port" in case:
            reachability = probe_tcp(args.kerio_host, case["port"])
            result["reachability"] = reachability
            if not reachability["reachable"]:
                result["status"] = "skipped_by_stand_limits"
                result["reason"] = f"{case['transport']} is not reachable: {reachability['message']}"
                results.append(result)
                continue

        try:
            exercise_payload = exercise_case(case, args, actor)
            result["exercise"] = exercise_payload
            verification = wait_for_audit_match(
                args=args,
                before_lines=before_lines,
                protocol=case["protocol"],
                expected_user=expected_user,
            )
            if verification["found"]:
                result["status"] = "passed"
                result["matched_line"] = verification["match"]["line"]
                result["matched_at"] = verification["match"]["timestamp"]
                result["source_ip"] = verification["match"]["ip"]
                if verification["match"].get("user_agent"):
                    result["user_agent"] = verification["match"]["user_agent"]
                if elastic_password:
                    elastic_verification = wait_for_elastic_case_match(
                        args=args,
                        elastic_password=elastic_password,
                        protocol=case["protocol"],
                        actor_email=expected_user,
                        started_at=result["started_at"],
                    )
                    result["elastic_check"] = elastic_verification
                    if elastic_verification["found"]:
                        result["elastic_hit"] = elastic_verification["payload"]["hits"][0]["_source"]
                    else:
                        result["status"] = "failed"
                        result["reason"] = (
                            "Audit entry was observed in Kerio audit.log but was not confirmed in Elasticsearch "
                            "within the verification timeout"
                        )
            else:
                result["status"] = "failed"
                result["reason"] = "Audit entry was not observed within the verification timeout"
        except Exception as exc:
            result["status"] = "failed"
            result["reason"] = str(exc)

        result["finished_at"] = utc_now_iso()
        results.append(result)

    elastic_check: dict[str, Any] | None = None
    if elastic_password:
        elastic_check = {
            "checked_cases": 0,
            "confirmed_cases": 0,
            "case_results": [],
        }
        for row in results:
            if "elastic_check" not in row:
                continue
            payload = row["elastic_check"]["payload"]
            elastic_check["checked_cases"] += 1
            if row["elastic_check"]["found"]:
                elastic_check["confirmed_cases"] += 1
            elastic_check["case_results"].append(
                {
                    "case_id": row["case_id"],
                    "protocol": row["protocol"],
                    "actor_email": row["actor_email"],
                    "hit_count": payload.get("hit_count", 0),
                }
            )
        try:
            elastic_check["recent_hits"] = elastic_query(
                elastic_url=args.elastic_url,
                username=args.elastic_user,
                password=elastic_password,
                actor_emails=[row["actor_email"] for row in results if row.get("actor_email")],
                lookback=args.elastic_lookback,
            )
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as exc:
            elastic_check["error"] = str(exc)

    summary = {
        "planned": len(CASE_SPECS),
        "passed": sum(1 for row in results if row["status"] == "passed"),
        "failed": sum(1 for row in results if row["status"] == "failed"),
        "skipped": sum(1 for row in results if row["status"] == "skipped_by_stand_limits"),
        "manual_required": len(MANUAL_CASES),
    }

    payload = {
        "generated_at": utc_now_iso(),
        "run_id": args.run_id,
        "identities_file": str(args.identities_file),
        "kerio_host": args.kerio_host,
        "recent_observed_protocols": recent_observed_protocols(recent_before),
        "cases": results,
        "manual_cases": MANUAL_CASES,
        "summary": summary,
    }
    if elastic_check is not None:
        payload["elastic_check"] = elastic_check

    ensure_dir(args.output_dir)
    write_json(args.output_dir / "audit_results.json", payload)
    (args.output_dir / "audit_summary.md").write_text(build_markdown_report(payload), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
