"""
Exports all rows from raw.decision_hits to CSV in data/processed/.

Run:
    docker compose exec python python analysis/export_decision_hits_csv.py
"""

from __future__ import annotations

import csv
import os
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import psycopg2
import psycopg2.extras

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
OUTPUT_PATH = _PROJECT_ROOT / "data" / "processed" / "decision_hits.csv"

SCHEMA = "raw"
TABLE = "decision_hits"


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def _serialize(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Decimal):
        return str(value)
    return str(value)


def fetch_decision_hits(conn) -> tuple[list[str], list[dict]]:
    sql = f"""
        SELECT *
        FROM {SCHEMA}.{TABLE}
        ORDER BY "loadedAt", "hit_id"
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = [dict(row) for row in cur.fetchall()]
        fieldnames = [col.name for col in cur.description] if cur.description else []
    return fieldnames, rows


def export_decision_hits_csv() -> int:
    conn = get_connection()
    try:
        fieldnames, rows = fetch_decision_hits(conn)
    except psycopg2.Error as exc:
        print(f"Query failed ({SCHEMA}.{TABLE}): {exc}")
        print(
            "Run load_decision_hits first: "
            "docker compose exec python python ingestion/load_decision_hits.py"
        )
        return 1
    finally:
        conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize(row[key]) for key in fieldnames})

    print(f"Exported {len(rows)} row(s) to {OUTPUT_PATH}")
    return 0


def main() -> None:
    raise SystemExit(export_decision_hits_csv())


if __name__ == "__main__":
    main()
