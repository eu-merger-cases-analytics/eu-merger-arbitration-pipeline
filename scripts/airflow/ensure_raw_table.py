#!/usr/bin/env python3
"""
Run init SQL only when a raw table is missing (first-time setup).

Usage (from Airflow via compose_exec):
  python .../ensure_raw_table.py decisions
  python .../ensure_raw_table.py hits
"""

from __future__ import annotations

import subprocess
import sys

DB_CONTAINER = "eu-merger-arbitration-db"
DB_NAME = "eu-merger-arbitration"
DB_USER = "user"

TABLES = {
    "decisions": ("raw.decisions", "/init/create_raw_schema.sql"),
    "hits": ("raw.decision_hits", "/init/create_raw_decision_hits.sql"),
}


def _regclass_exists(regclass: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            DB_CONTAINER,
            "psql",
            "-U",
            DB_USER,
            "-d",
            DB_NAME,
            "-tAc",
            f"SELECT to_regclass('{regclass}');",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    value = result.stdout.strip()
    return bool(value) and value.lower() != "null"


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in TABLES:
        print("Usage: ensure_raw_table.py <decisions|hits>", file=sys.stderr)
        raise SystemExit(1)

    key = sys.argv[1]
    regclass, sql_path = TABLES[key]

    if _regclass_exists(regclass):
        print(f"Skip init: {regclass} already exists")
        return

    print(f"Creating {regclass} using {sql_path}")
    subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            DB_CONTAINER,
            "psql",
            "-U",
            DB_USER,
            "-d",
            DB_NAME,
            "-f",
            sql_path,
        ],
        check=True,
    )
    print(f"Done: {regclass} initialized")


if __name__ == "__main__":
    main()
