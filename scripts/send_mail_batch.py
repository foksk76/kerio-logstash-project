#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mailtest_common import (
    DEFAULT_SCENARIO_PROFILE,
    SCENARIO_WEIGHT_PROFILES,
    allocate_scenarios,
    ensure_dir,
    load_json,
    scenario_weights_for_profile,
    utc_now_precise_iso,
    write_jsonl,
)

DEFAULT_MESSAGE_COUNT = 60
DEFAULT_SEND_RATE = 4.0
DEFAULT_MAILING_MIN_RECIPIENTS = 2
DEFAULT_MAILING_MAX_RECIPIENTS = 4
DEFAULT_MAILING_MAX_NONEXISTENT = 0
DEFAULT_NONEXISTENT_MIN_RECIPIENTS = 1
DEFAULT_NONEXISTENT_MAX_RECIPIENTS = 1
DEFAULT_ALIASES_MIN_RECIPIENTS = 1
DEFAULT_ALIASES_MAX_RECIPIENTS = 1
DEFAULT_MIXED_EXTRA_MAX = 1


class RateLimiter:
    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("send-rate must be greater than zero")
        self.interval = 1.0 / rate_per_second
        self.next_slot = time.monotonic()

    def wait(self) -> None:
        now = time.monotonic()
        if self.next_slot > now:
            time.sleep(self.next_slot - now)
            now = time.monotonic()
        self.next_slot = max(self.next_slot, now) + self.interval


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send a constrained-random Kerio mail batch.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--identities-file", type=Path, required=True)
    parser.add_argument("--message-count", type=int, default=DEFAULT_MESSAGE_COUNT)
    parser.add_argument("--send-rate", type=float, default=DEFAULT_SEND_RATE)
    parser.add_argument(
        "--scenario-profile",
        default=DEFAULT_SCENARIO_PROFILE,
        choices=tuple(SCENARIO_WEIGHT_PROFILES.keys()),
    )
    parser.add_argument("--mailing-min-recipients", type=int, default=DEFAULT_MAILING_MIN_RECIPIENTS)
    parser.add_argument("--mailing-max-recipients", type=int, default=DEFAULT_MAILING_MAX_RECIPIENTS)
    parser.add_argument("--mailing-max-nonexistent", type=int, default=DEFAULT_MAILING_MAX_NONEXISTENT)
    parser.add_argument("--nonexistent-min-recipients", type=int, default=DEFAULT_NONEXISTENT_MIN_RECIPIENTS)
    parser.add_argument("--nonexistent-max-recipients", type=int, default=DEFAULT_NONEXISTENT_MAX_RECIPIENTS)
    parser.add_argument("--aliases-min-recipients", type=int, default=DEFAULT_ALIASES_MIN_RECIPIENTS)
    parser.add_argument("--aliases-max-recipients", type=int, default=DEFAULT_ALIASES_MAX_RECIPIENTS)
    parser.add_argument("--mixed-extra-max", type=int, default=DEFAULT_MIXED_EXTRA_MAX)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--smtp-host", default="127.0.0.1")
    parser.add_argument("--smtp-port", type=int, default=25)
    parser.add_argument("--smtp-timeout", type=int, default=30)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def validate_range(name: str, minimum: int, maximum: int) -> None:
    if minimum < 0:
        raise ValueError(f"{name} minimum must be zero or greater")
    if maximum < minimum:
        raise ValueError(f"{name} maximum must be greater than or equal to minimum")


def validate_args(args: argparse.Namespace) -> None:
    validate_range("mailing recipients", args.mailing_min_recipients, args.mailing_max_recipients)
    validate_range("nonexistent recipients", args.nonexistent_min_recipients, args.nonexistent_max_recipients)
    validate_range("alias recipients", args.aliases_min_recipients, args.aliases_max_recipients)
    if args.mailing_max_nonexistent < 0:
        raise ValueError("mailing-max-nonexistent must be zero or greater")
    if args.mixed_extra_max < 0:
        raise ValueError("mixed-extra-max must be zero or greater")


def choose_sample(
    rng: random.Random,
    candidates: list[str],
    minimum: int,
    maximum: int,
    label: str,
) -> list[str]:
    if len(candidates) < minimum:
        raise RuntimeError(f"Not enough {label}: need at least {minimum}, have {len(candidates)}")
    count = rng.randint(minimum, min(maximum, len(candidates)))
    return sorted(rng.sample(candidates, count))


def choose_sender(rng: random.Random, sender_pool: list[str]) -> str:
    return rng.choice(sender_pool)


def choose_real_recipients(rng: random.Random, real_pool: list[str], sender: str, minimum: int, maximum: int) -> list[str]:
    candidates = [address for address in real_pool if address != sender]
    if not candidates:
        raise RuntimeError("No real recipients available after excluding sender")
    return choose_sample(rng, candidates, minimum, maximum, "real recipients")


def choose_alias_recipients(
    rng: random.Random,
    alias_pool: list[dict[str, str]],
    sender: str,
    minimum: int,
    maximum: int,
) -> list[str]:
    candidates = [item["alias"] for item in alias_pool if item["target"] != sender]
    if not candidates:
        candidates = [item["alias"] for item in alias_pool]
    return choose_sample(rng, candidates, minimum, maximum, "alias recipients")


def choose_nonexistent_recipients(rng: random.Random, nonexistent_pool: list[str], minimum: int, maximum: int) -> list[str]:
    return choose_sample(rng, nonexistent_pool, minimum, maximum, "nonexistent recipients")


def plan_message(
    rng: random.Random,
    scenario: str,
    sequence: int,
    run_id: str,
    sender_pool: list[str],
    real_pool: list[str],
    alias_pool: list[dict[str, str]],
    nonexistent_pool: list[str],
    args: argparse.Namespace,
) -> dict[str, Any]:
    sender = choose_sender(rng, sender_pool)
    recipients: list[str] = []
    expected = {"success_flow": False, "raw_failure": False}

    if scenario == "peer_to_peer":
        recipients = choose_real_recipients(rng, real_pool, sender, 1, 1)
        expected["success_flow"] = True
    elif scenario == "mailing":
        recipients = choose_real_recipients(
            rng,
            real_pool,
            sender,
            args.mailing_min_recipients,
            args.mailing_max_recipients,
        )
        fake_count = rng.randint(0, args.mailing_max_nonexistent)
        if fake_count:
            recipients.extend(choose_nonexistent_recipients(rng, nonexistent_pool, fake_count, fake_count))
            expected["raw_failure"] = True
        expected["success_flow"] = True
    elif scenario == "nonexistent":
        recipients = choose_nonexistent_recipients(
            rng,
            nonexistent_pool,
            args.nonexistent_min_recipients,
            args.nonexistent_max_recipients,
        )
        expected["raw_failure"] = True
    elif scenario == "aliases_only":
        recipients = choose_alias_recipients(
            rng,
            alias_pool,
            sender,
            args.aliases_min_recipients,
            args.aliases_max_recipients,
        )
        expected["success_flow"] = True
    elif scenario == "real_plus_aliases":
        recipients = choose_real_recipients(rng, real_pool, sender, 1, 1)
        recipients.extend(choose_alias_recipients(rng, alias_pool, sender, 1, 1))
        extra_budget = rng.randint(0, args.mixed_extra_max)
        for _ in range(extra_budget):
            if rng.random() < 0.5:
                recipient = choose_real_recipients(rng, real_pool, sender, 1, 1)[0]
            else:
                recipient = choose_alias_recipients(rng, alias_pool, sender, 1, 1)[0]
            if recipient not in recipients and recipient != sender:
                recipients.append(recipient)
        expected["success_flow"] = True
    else:
        raise ValueError(f"Unsupported scenario: {scenario}")

    recipients = sorted(dict.fromkeys(recipient for recipient in recipients if recipient != sender))
    subject = f"KT-{run_id}-{sequence:04d}-{scenario}"
    message_id = f"<KT-{run_id}-{sequence:04d}@kerio.lo>"

    return {
        "run_id": run_id,
        "sequence": sequence,
        "scenario": scenario,
        "sender": sender,
        "to": recipients,
        "subject": subject,
        "message_id": message_id,
        "x_test_run": run_id,
        "x_test_scenario": scenario,
        "send_rate_limit": None,
        "planned_at": None,
        "sent_at": None,
        "expected": expected,
        "send_status": "planned",
        "send_error": None,
    }


def build_body(message_plan: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"run_id: {message_plan['run_id']}",
            f"sequence: {message_plan['sequence']}",
            f"scenario: {message_plan['scenario']}",
            f"sender: {message_plan['sender']}",
            f"recipients: {', '.join(message_plan['to'])}",
            "",
            "Kerio log pipeline batch test.",
        ]
    )


def send_one_message(
    host: str,
    port: int,
    timeout: int,
    message_plan: dict[str, Any],
) -> None:
    email = EmailMessage()
    email["From"] = message_plan["sender"]
    email["To"] = ", ".join(message_plan["to"])
    email["Subject"] = message_plan["subject"]
    email["Message-ID"] = message_plan["message_id"]
    email["X-Test-Run"] = message_plan["x_test_run"]
    email["X-Test-Scenario"] = message_plan["x_test_scenario"]
    email.set_content(build_body(message_plan))

    with smtplib.SMTP(host, port, timeout=timeout) as smtp:
        smtp.send_message(email)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    validate_args(args)
    rng = random.Random(args.seed)

    identities = load_json(args.identities_file)
    sender_pool = identities["sender_pool"]
    real_pool = identities["real_recipient_pool"]
    alias_pool = identities["alias_pool"]
    nonexistent_pool = identities["nonexistent_pool"]

    scenario_weights = scenario_weights_for_profile(args.scenario_profile)
    allocations = allocate_scenarios(args.message_count, scenario_weights)
    scenario_stream: list[str] = []
    for scenario, count in allocations.items():
        scenario_stream.extend([scenario] * count)
    rng.shuffle(scenario_stream)

    ensure_dir(args.output_dir)
    limiter = RateLimiter(args.send_rate)
    messages: list[dict[str, Any]] = []

    for sequence, scenario in enumerate(scenario_stream, start=1):
        message_plan = plan_message(
            rng=rng,
            scenario=scenario,
            sequence=sequence,
            run_id=args.run_id,
            sender_pool=sender_pool,
            real_pool=real_pool,
            alias_pool=alias_pool,
            nonexistent_pool=nonexistent_pool,
            args=args,
        )
        message_plan["send_rate_limit"] = args.send_rate
        message_plan["planned_at"] = utc_now_precise_iso()
        limiter.wait()

        try:
            if not args.dry_run:
                send_one_message(
                    host=args.smtp_host,
                    port=args.smtp_port,
                    timeout=args.smtp_timeout,
                    message_plan=message_plan,
                )
            message_plan["send_status"] = "sent" if not args.dry_run else "dry_run"
            message_plan["sent_at"] = utc_now_precise_iso()
        except Exception as exc:  # pragma: no cover - network behavior
            message_plan["send_status"] = "error"
            message_plan["sent_at"] = utc_now_precise_iso()
            message_plan["send_error"] = str(exc)

        messages.append(message_plan)

    write_jsonl(args.output_dir / "messages.jsonl", messages)

    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "message_count": len(messages),
                "send_rate": args.send_rate,
                "scenario_profile": args.scenario_profile,
                "scenario_weights": scenario_weights,
                "allocations": allocations,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
