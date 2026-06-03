"""
Exports all rows from marts.mart_arbitration_decisions to CSV in data/processed/.

Run:
    docker compose exec python python analysis/export_mart_arbitration_decisions_csv.py
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
OUTPUT_PATH = _PROJECT_ROOT / "data" / "processed" / "mart_arbitration_decisions.csv"

SCHEMA = "marts"
TABLE = "mart_arbitration_decisions"


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


def fetch_mart(conn) -> tuple[list[str], list[dict]]:
    sql = f"""
        SELECT *
        FROM {SCHEMA}.{TABLE}
        ORDER BY decision_adoption_date NULLS LAST, case_number, decision_number
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = [dict(row) for row in cur.fetchall()]
        fieldnames = [col.name for col in cur.description] if cur.description else []
    return fieldnames, rows


def main() -> None:
    conn = get_connection()
    try:
        fieldnames, rows = fetch_mart(conn)
    except psycopg2.Error as exc:
        print(f"Query failed ({SCHEMA}.{TABLE}): {exc}")
        print(
            "Run dbt first: docker compose exec dbt bash -c "
            "'cd eu_merger_arbitration && dbt run --select mart_arbitration_decisions --profiles-dir .'"
        )
        raise SystemExit(1) from exc
    finally:
        conn.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _serialize(row[key]) for key in fieldnames})

    print(f"Exported {len(rows)} row(s) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
