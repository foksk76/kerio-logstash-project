#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCENARIO_WEIGHTS = {
    "peer_to_peer": 0.25,
    "mailing": 0.25,
    "nonexistent": 0.25,
    "aliases_only": 0.12,
    "real_plus_aliases": 0.13,
}


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def utc_now_precise_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def slugify_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", ".", normalized)
    normalized = normalized.strip(".")
    normalized = re.sub(r"\.{2,}", ".", normalized)
    return normalized or "user"


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def allocate_scenarios(message_count: int) -> dict[str, int]:
    raw_allocations: list[tuple[float, str]] = []
    scenario_counts: dict[str, int] = {}

    total_assigned = 0
    for scenario, weight in SCENARIO_WEIGHTS.items():
        raw_value = message_count * weight
        base_value = math.floor(raw_value)
        scenario_counts[scenario] = base_value
        total_assigned += base_value
        raw_allocations.append((raw_value - base_value, scenario))

    for _, scenario in sorted(raw_allocations, reverse=True):
        if total_assigned >= message_count:
            break
        scenario_counts[scenario] += 1
        total_assigned += 1

    return scenario_counts

