#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
import string
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.mailtest_common import ensure_dir, slugify_ascii, utc_now_iso, write_json

try:
    from faker import Faker
except ImportError:  # pragma: no cover - optional dependency
    Faker = None

FALLBACK_FIRST_NAMES = [
    "Alice",
    "Bob",
    "Carol",
    "David",
    "Eve",
    "Frank",
    "Grace",
    "Heidi",
    "Ivan",
    "Judy",
    "Mallory",
    "Niaj",
    "Olivia",
    "Peggy",
    "Sybil",
]

FALLBACK_LAST_NAMES = [
    "Anderson",
    "Brown",
    "Clark",
    "Davis",
    "Evans",
    "Foster",
    "Green",
    "Hill",
    "Irwin",
    "Jones",
    "King",
    "Lewis",
    "Moore",
    "Nash",
    "Owens",
]

DEFAULT_PASSWORD_LENGTH = 12
# Kerio documents this class of allowed non-alphanumeric characters for
# password-complexity checks. We use a conservative subset that is CSV-safe.
PASSWORD_SPECIALS = "!#$%^&*_-+=?"
KERIO_USER_FIELDNAMES = [
    "Name",
    "Password",
    "FullName",
    "Description",
    "Enable",
    "DataSource",
    "Authentication",
    "Role",
    "Groups",
    "MailAddress",
    "EmailForwarding",
    "ItemLimit",
    "DiskSizeLimit (kB)",
    "ConsumedItems",
    "ConsumedSize (kB)",
    "OutgoingMessageLimit (kB)",
    "LastLogin (UTC)",
    "PublishInGAL",
    "CleanOutItems",
    "DomainRestriction",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate mailbox, alias, and nonexistent identity manifests.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--domain", default="kerio.lo")
    parser.add_argument("--new-mailboxes", type=int, default=10)
    parser.add_argument("--sender-count", type=int, default=9)
    parser.add_argument("--alias-min", type=int, default=0)
    parser.add_argument("--alias-max", type=int, default=3)
    parser.add_argument("--alias-total-min", type=int, default=6)
    parser.add_argument("--nonexistent-count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--password-length", type=int, default=DEFAULT_PASSWORD_LENGTH)
    parser.add_argument("--default-password", default=None)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser


def build_name_source(seed: int | None):
    rng = random.Random(seed)
    fake = None
    if Faker is not None:
        fake = Faker()
        if seed is not None:
            Faker.seed(seed)
            fake.seed_instance(seed)

    def next_name() -> tuple[str, str]:
        if fake is not None:
            return fake.first_name(), fake.last_name()
        return rng.choice(FALLBACK_FIRST_NAMES), rng.choice(FALLBACK_LAST_NAMES)

    return rng, next_name


def unique_local_part(base: str, used: set[str]) -> str:
    candidate = base
    suffix = 1
    while candidate in used:
        candidate = f"{base}.{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def forbidden_password_fragments(local_part: str, domain: str, display_name: str) -> set[str]:
    fragments: set[str] = set()

    def add_fragments(value: str) -> None:
        normalized = slugify_ascii(value).replace("-", ".")
        pieces = [piece for piece in normalized.split(".") if len(piece) >= 3]
        for piece in pieces:
            fragments.add(piece.lower())

    add_fragments(local_part)
    add_fragments(domain)
    for token in display_name.split():
        add_fragments(token)

    return fragments


def generate_password(
    password_length: int,
    rng: random.Random,
    used: set[str],
    forbidden_fragments: set[str],
) -> str:
    if password_length < 4:
        raise ValueError("password_length must be at least 4")

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    specials = PASSWORD_SPECIALS
    alphabet = lower + upper + digits + specials

    while True:
        chars = [
            rng.choice(lower),
            rng.choice(upper),
            rng.choice(digits),
            rng.choice(specials),
        ]
        chars.extend(rng.choice(alphabet) for _ in range(password_length - 4))
        rng.shuffle(chars)
        password = "".join(chars)
        lowered = password.lower()
        if password not in used and not any(fragment in lowered for fragment in forbidden_fragments):
            used.add(password)
            return password


def generate_users(args: argparse.Namespace) -> list[dict[str, Any]]:
    rng, next_name = build_name_source(args.seed)
    used_local_parts: set[str] = {"doge"}
    used_passwords: set[str] = set()
    users: list[dict[str, Any]] = []

    while len(users) < args.new_mailboxes:
        first_name, last_name = next_name()
        display_name = f"{first_name} {last_name}"
        base_local_part = slugify_ascii(display_name)
        local_part = unique_local_part(base_local_part, used_local_parts)
        users.append(
            {
                "login": local_part,
                "address": f"{local_part}@{args.domain}",
                "display_name": display_name,
                "password": args.default_password
                or generate_password(
                    args.password_length,
                    rng,
                    used_passwords,
                    forbidden_password_fragments(local_part, args.domain, display_name),
                ),
                "aliases": [],
                "can_send": False,
            }
        )

    selected_sender_logins = {user["login"] for user in rng.sample(users, k=min(args.sender_count, len(users)))}
    for user in users:
        user["can_send"] = user["login"] in selected_sender_logins

    return users


def alias_candidates(user: dict[str, Any]) -> list[str]:
    local_part = user["login"]
    pieces = local_part.split(".")
    first = pieces[0]
    last = pieces[-1]
    return [
        f"{first[0]}.{last}",
        f"{first}.{last[0]}",
        f"{first[0]}{last}",
        f"{first}-{last}",
        f"{first}.{last}.team",
        f"{first}.{last}.mail",
    ]


def generate_aliases(
    users: list[dict[str, Any]],
    domain: str,
    alias_min: int,
    alias_max: int,
    alias_total_min: int,
    seed: int | None,
) -> list[dict[str, str]]:
    attempt_seed = seed
    aliases: list[dict[str, str]] = []

    for _ in range(32):
        rng = random.Random(attempt_seed)
        aliases = []
        used_addresses = {user["address"] for user in users}
        used_local_parts = {user["login"] for user in users}

        for user in users:
            user["aliases"] = []
            alias_count = rng.randint(alias_min, alias_max)
            candidates = alias_candidates(user)
            rng.shuffle(candidates)

            for candidate in candidates:
                if len(user["aliases"]) >= alias_count:
                    break
                candidate = slugify_ascii(candidate)
                if candidate in used_local_parts:
                    continue
                alias_address = f"{candidate}@{domain}"
                if alias_address in used_addresses:
                    continue
                used_local_parts.add(candidate)
                used_addresses.add(alias_address)
                user["aliases"].append(alias_address)
                aliases.append({"alias": alias_address, "target": user["address"]})

        if len(aliases) >= alias_total_min:
            return aliases

        attempt_seed = (attempt_seed or 0) + 1

    raise RuntimeError("Unable to generate a sufficiently large alias pool.")


def generate_nonexistent_pool(domain: str, count: int, reserved: set[str], seed: int | None) -> list[str]:
    rng = random.Random((seed or 0) + 1000)
    pool: list[str] = []
    index = 1

    while len(pool) < count:
        local_part = f"ghost.user.{index:03d}"
        address = f"{local_part}@{domain}"
        if address not in reserved:
            pool.append(address)
            reserved.add(address)
        index += 1
        if rng.random() < 0.25:
            index += 1

    return pool


def write_mailboxes_csv(path: Path, users: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["login", "address", "display_name", "password", "can_send"],
        )
        writer.writeheader()
        writer.writerows(
            {
                "login": user["login"],
                "address": user["address"],
                "display_name": user["display_name"],
                "password": user["password"],
                "can_send": "yes" if user["can_send"] else "no",
            }
            for user in users
        )


def write_ui_aliases_csv(path: Path, aliases: list[dict[str, str]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["alias", "deliver_to", "description"])
        writer.writeheader()
        writer.writerows(
            {
                "alias": item["alias"].split("@", 1)[0],
                "deliver_to": item["target"],
                "description": "",
            }
            for item in aliases
        )


def kerio_mail_addresses(user: dict[str, Any]) -> str:
    return user["login"]


def write_kerio_import_csv(path: Path, users: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=KERIO_USER_FIELDNAMES,
            delimiter=";",
        )
        writer.writeheader()
        for user in users:
            writer.writerow(
                {
                    "Name": user["login"],
                    "Password": user["password"],
                    "FullName": user["display_name"],
                    "Description": "",
                    "Enable": "Yes",
                    "DataSource": "Internal",
                    "Authentication": "Internal",
                    "Role": "No rights",
                    "Groups": "",
                    "MailAddress": kerio_mail_addresses(user),
                    "EmailForwarding": "",
                    "ItemLimit": "",
                    "DiskSizeLimit (kB)": "",
                    "ConsumedItems": "0",
                    "ConsumedSize (kB)": "0",
                    "OutgoingMessageLimit (kB)": "",
                    "LastLogin (UTC)": "",
                    "PublishInGAL": "Yes",
                    "CleanOutItems": "Domain defined",
                    "DomainRestriction": "No",
                }
            )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    output_dir = ensure_dir(args.output_dir)
    users = generate_users(args)
    aliases = generate_aliases(
        users=users,
        domain=args.domain,
        alias_min=args.alias_min,
        alias_max=args.alias_max,
        alias_total_min=args.alias_total_min,
        seed=args.seed,
    )

    reserved = {"doge@" + args.domain}
    reserved.update(user["address"] for user in users)
    reserved.update(alias["alias"] for alias in aliases)
    nonexistent_pool = generate_nonexistent_pool(
        domain=args.domain,
        count=args.nonexistent_count,
        reserved=reserved,
        seed=args.seed,
    )

    sender_pool = ["doge@" + args.domain] + [user["address"] for user in users if user["can_send"]]
    real_recipient_pool = ["doge@" + args.domain] + [user["address"] for user in users]

    payload = {
        "generated_at": utc_now_iso(),
        "run_id": args.run_id,
        "domain": args.domain,
        "control_mailbox": "doge@" + args.domain,
        "sender_pool": sender_pool,
        "real_recipient_pool": real_recipient_pool,
        "alias_pool": aliases,
        "nonexistent_pool": nonexistent_pool,
        "users": users,
    }

    write_json(output_dir / "identities.json", payload)
    write_mailboxes_csv(output_dir / "provision_mailboxes.csv", users)
    write_ui_aliases_csv(output_dir / "ui_aliases.csv", aliases)
    write_kerio_import_csv(output_dir / "kerio_import_users.csv", users)

    print(f"Generated identities for run {args.run_id}")
    print(f"Real mailboxes: {len(real_recipient_pool)}")
    print(f"Senders: {len(sender_pool)}")
    print(f"Aliases: {len(aliases)}")
    print(f"Nonexistent addresses: {len(nonexistent_pool)}")
    print(f"Kerio import CSV: {output_dir / 'kerio_import_users.csv'}")
    print(f"Kerio UI aliases CSV: {output_dir / 'ui_aliases.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
