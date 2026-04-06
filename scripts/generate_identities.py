#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import random
import string
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.kerio_api import DEFAULT_KERIO_API_URL, KerioAdminClient, env_or_dotenv
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
DEFAULT_CONTROL_MAILBOX = "doge"
# Kerio documents this class of allowed non-alphanumeric characters for
# password-complexity checks. We use a conservative ASCII subset.
PASSWORD_SPECIALS = "!#$%^&*_-+=?"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate mailbox, alias, and nonexistent identity manifests.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--domain", default="kerio.lo")
    parser.add_argument("--control-mailbox", default=DEFAULT_CONTROL_MAILBOX)
    parser.add_argument("--new-mailboxes", type=int, default=10)
    parser.add_argument("--sender-count", type=int, default=9)
    parser.add_argument("--alias-min", type=int, default=0)
    parser.add_argument("--alias-max", type=int, default=3)
    parser.add_argument("--alias-total-min", type=int, default=6)
    parser.add_argument("--nonexistent-count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--password-length", type=int, default=DEFAULT_PASSWORD_LENGTH)
    parser.add_argument("--default-password", default=None)
    parser.add_argument("--skip-kerio-provision", action="store_true")
    parser.add_argument("--keep-existing-run-users", action="store_true")
    parser.add_argument("--kerio-api-url", default=DEFAULT_KERIO_API_URL)
    parser.add_argument("--kerio-api-user-env", default="KERIO_API_USER")
    parser.add_argument("--kerio-api-password-env", default="KERIO_API_PASSWORD")
    parser.add_argument("--kerio-env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--kerio-verify-tls", action="store_true")
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


def effective_seed(run_id: str, seed: int | None) -> int:
    if seed is not None:
        return seed
    return int(hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:16], 16)


def build_managed_prefix(run_id: str) -> str:
    slug = slugify_ascii(run_id).replace(".", "")[:8] or "run"
    token = hashlib.sha1(run_id.encode("utf-8")).hexdigest()[:6]
    return f"kt.{slug}.{token}"


def build_managed_description(run_id: str) -> str:
    return f"kerio-logstash managed run {run_id}"


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
    rng, next_name = build_name_source(args.effective_seed)
    used_local_parts: set[str] = {args.control_mailbox}
    used_passwords: set[str] = set()
    users: list[dict[str, Any]] = []

    while len(users) < args.new_mailboxes:
        first_name, last_name = next_name()
        display_name = f"{first_name} {last_name}"
        base_local_part = slugify_ascii(display_name)
        local_part = unique_local_part(f"{args.managed_prefix}.{base_local_part}", used_local_parts)
        users.append(
            {
                "login": local_part,
                "base_login": base_local_part,
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
                "alias_local_parts": [],
                "can_send": False,
                "managed_prefix": args.managed_prefix,
                "description": args.managed_description,
            }
        )

    selected_sender_logins = {user["login"] for user in rng.sample(users, k=min(args.sender_count, len(users)))}
    for user in users:
        user["can_send"] = user["login"] in selected_sender_logins

    return users


def alias_candidates(user: dict[str, Any]) -> list[str]:
    pieces = [piece for piece in user["base_login"].split(".") if piece]
    first = pieces[0]
    last = pieces[-1]
    return [
        f"{user['managed_prefix']}.alias.{first[0]}.{last}",
        f"{user['managed_prefix']}.alias.{first}.{last[0]}",
        f"{user['managed_prefix']}.alias.{first[0]}{last}",
        f"{user['managed_prefix']}.alias.{first}-{last}",
        f"{user['managed_prefix']}.alias.{first}.{last}.team",
        f"{user['managed_prefix']}.alias.{first}.{last}.mail",
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
            user["alias_local_parts"] = []
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
                user["alias_local_parts"].append(candidate)
                aliases.append(
                    {
                        "alias": alias_address,
                        "alias_local_part": candidate,
                        "target": user["address"],
                        "target_login": user["login"],
                    }
                )

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


def kerio_user_create_payload(user: dict[str, Any], domain_id: str) -> dict[str, Any]:
    return {
        "domainId": domain_id,
        "loginName": user["login"],
        "fullName": user["display_name"],
        "description": user["description"],
        "isEnabled": True,
        "itemSource": "DSInternalSource",
        "authType": "UInternalAuth",
        "password": user["password"],
        "role": {
            "userRole": "UserRole",
            "publicFolderRight": False,
            "archiveFolderRight": False,
        },
        "emailAddresses": [],
        "hasDomainRestriction": False,
        "publishInGal": False,
        "allowPasswordChange": False,
        "hasDefaultSpamRule": False,
    }


def wait_for_absent_logins(
    client: KerioAdminClient,
    *,
    domain_id: str,
    expected_absent: list[str],
    timeout_seconds: int = 30,
) -> None:
    if not expected_absent:
        return

    deadline = time.monotonic() + timeout_seconds
    remaining = set(expected_absent)
    while remaining and time.monotonic() < deadline:
        current = client.users_by_login(domain_id, ["id", "loginName"])
        remaining = {login for login in remaining if login in current}
        if remaining:
            time.sleep(1)

    if remaining:
        raise SystemExit(
            "Kerio did not finish removing managed users in time: "
            + ", ".join(sorted(remaining))
        )


def provision_kerio_entities(
    args: argparse.Namespace,
    users: list[dict[str, Any]],
) -> dict[str, Any]:
    api_user = env_or_dotenv(args.kerio_api_user_env, args.kerio_env_file)
    api_password = env_or_dotenv(args.kerio_api_password_env, args.kerio_env_file)
    if not api_user or not api_password:
        raise SystemExit(
            f"Kerio API credentials are required via {args.kerio_api_user_env}/{args.kerio_api_password_env} "
            f"or {args.kerio_env_file}"
        )

    alias_local_parts_by_login = {user["login"]: sorted(user["alias_local_parts"]) for user in users}

    with KerioAdminClient(
        api_url=args.kerio_api_url,
        username=api_user,
        password=api_password,
        verify_tls=args.kerio_verify_tls,
    ) as client:
        domain = client.get_domain(args.domain)
        before = client.users_by_login(domain["id"], ["id", "loginName", "description"])

        removed_users: list[str] = []
        if not args.keep_existing_run_users:
            removed_users = [
                item["loginName"]
                for item in before.values()
                if item.get("description") == args.managed_description
            ]
            client.remove_users(
                [
                    item["id"]
                    for item in before.values()
                    if item.get("description") == args.managed_description
                ]
            )
            wait_for_absent_logins(client, domain_id=domain["id"], expected_absent=removed_users)
            before = client.users_by_login(domain["id"], ["id", "loginName", "description"])

        reusable: dict[str, str] = {}
        collisions: list[str] = []
        for user in users:
            existing = before.get(user["login"])
            if not existing:
                continue
            if existing.get("description") == args.managed_description:
                reusable[user["login"]] = existing["id"]
            else:
                collisions.append(user["login"])

        if collisions:
            raise SystemExit(
                "Kerio login collision with existing non-managed users: "
                + ", ".join(sorted(collisions))
            )

        create_payloads = [
            kerio_user_create_payload(user, domain["id"])
            for user in users
            if user["login"] not in reusable
        ]
        created_rows = client.create_users(create_payloads) if create_payloads else []

        users_after_create = client.users_by_login(domain["id"], ["id", "loginName", "description"])
        provisioned_users: list[dict[str, Any]] = []
        for user in users:
            current = users_after_create.get(user["login"])
            if not current:
                raise SystemExit(f"Kerio user {user['login']} was not found after provisioning")
            client.set_user_email_addresses(
                domain_id=domain["id"],
                user_id=current["id"],
                email_local_parts=alias_local_parts_by_login[user["login"]],
            )
            provisioned_users.append(
                {
                    "login": user["login"],
                    "address": user["address"],
                    "user_id": current["id"],
                    "alias_local_parts": alias_local_parts_by_login[user["login"]],
                    "aliases": user["aliases"],
                    "action": "reused" if user["login"] in reusable else "created",
                }
            )

    return {
        "enabled": True,
        "mode": "kerio_api_users_email_addresses",
        "domain": args.domain,
        "managed_prefix": args.managed_prefix,
        "managed_description": args.managed_description,
        "removed_same_run_users": sorted(removed_users),
        "created_count": len([item for item in provisioned_users if item["action"] == "created"]),
        "reused_count": len([item for item in provisioned_users if item["action"] == "reused"]),
        "created_result_rows": created_rows,
        "users": provisioned_users,
    }


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    args.effective_seed = effective_seed(args.run_id, args.seed)
    args.managed_prefix = build_managed_prefix(args.run_id)
    args.managed_description = build_managed_description(args.run_id)

    output_dir = ensure_dir(args.output_dir)
    users = generate_users(args)
    aliases = generate_aliases(
        users=users,
        domain=args.domain,
        alias_min=args.alias_min,
        alias_max=args.alias_max,
        alias_total_min=args.alias_total_min,
        seed=args.effective_seed,
    )

    reserved = {f"{args.control_mailbox}@{args.domain}"}
    reserved.update(user["address"] for user in users)
    reserved.update(alias["alias"] for alias in aliases)
    nonexistent_pool = generate_nonexistent_pool(
        domain=args.domain,
        count=args.nonexistent_count,
        reserved=reserved,
        seed=args.effective_seed,
    )

    provisioning = {
        "enabled": False,
        "mode": "skipped",
        "reason": "skip-kerio-provision",
    }
    if not args.skip_kerio_provision:
        provisioning = provision_kerio_entities(args, users)

    sender_pool = [f"{args.control_mailbox}@{args.domain}"] + [user["address"] for user in users if user["can_send"]]
    real_recipient_pool = [f"{args.control_mailbox}@{args.domain}"] + [user["address"] for user in users]

    payload = {
        "generated_at": utc_now_iso(),
        "run_id": args.run_id,
        "seed": args.effective_seed,
        "domain": args.domain,
        "control_mailbox": f"{args.control_mailbox}@{args.domain}",
        "managed_prefix": args.managed_prefix,
        "managed_description": args.managed_description,
        "sender_pool": sender_pool,
        "real_recipient_pool": real_recipient_pool,
        "alias_pool": aliases,
        "nonexistent_pool": nonexistent_pool,
        "users": users,
        "kerio_provisioning": provisioning,
    }

    write_json(output_dir / "identities.json", payload)
    write_json(output_dir / "kerio_provisioning.json", provisioning)

    print(f"Generated identities for run {args.run_id}")
    print(f"Effective seed: {args.effective_seed}")
    print(f"Managed prefix: {args.managed_prefix}")
    print(f"Real mailboxes: {len(real_recipient_pool)}")
    print(f"Senders: {len(sender_pool)}")
    print(f"Aliases: {len(aliases)}")
    print(f"Nonexistent addresses: {len(nonexistent_pool)}")
    print(f"Kerio provisioning: {provisioning['mode']}")
    print(f"Identity manifest: {output_dir / 'identities.json'}")
    print(f"Provisioning manifest: {output_dir / 'kerio_provisioning.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
