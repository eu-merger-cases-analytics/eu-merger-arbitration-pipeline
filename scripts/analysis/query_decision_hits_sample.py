"""
Fetches sample rows from raw.decision_hits and writes output to
query_decision_hits_sample_output.txt (overwrites on each run).

Run:
    docker compose exec python python analysis/query_decision_hits_sample.py

    docker compose exec -e ROW_LIMIT=5 python python analysis/query_decision_hits_sample.py
"""

import json
import os
from io import StringIO
from pathlib import Path

import psycopg2
import psycopg2.extras

OUTPUT_PATH = Path(__file__).resolve().parent / "query_decision_hits_sample_output.txt"

SCHEMA = "raw"
TABLE = "decision_hits"
ROW_LIMIT = 3


def get_connection():
    """Creates a database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def resolve_row_limit() -> int:
    """Row count from ROW_LIMIT env var, else ROW_LIMIT constant (minimum 1)."""
    raw = os.environ.get("ROW_LIMIT")
    limit = int(raw) if raw else ROW_LIMIT
    return max(1, limit)


def fetch_sample_rows(conn, limit: int) -> list[dict]:
    """Returns up to `limit` rows from raw.decision_hits (ordered by hit_id)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f'SELECT * FROM {SCHEMA}.{TABLE} '
            f'ORDER BY "hit_id" LIMIT %s',
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]


def format_row(row: dict) -> str:
    """Formats a row for human-readable output (sorted columns)."""
    lines = []
    for key in sorted(row.keys()):
        value = row[key]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def main() -> None:
    buf = StringIO()
    limit = resolve_row_limit()

    def out(text=""):
        print(text)
        buf.write(text + "\n")

    conn = get_connection()
    try:
        rows = fetch_sample_rows(conn, limit)
    finally:
        conn.close()

    if not rows:
        out(f"No rows found in {SCHEMA}.{TABLE}.")
        out("Run first: python ingestion/load_decision_hits.py")
    else:
        out(
            f"{len(rows)} row(s) from {SCHEMA}.{TABLE} "
            f"(ordered by hit_id, limit={limit}):"
        )
        for i, row in enumerate(rows, 1):
            out()
            out(
                f"--- Row {i} (hit_id={row.get('hit_id')}, "
                f"case={row.get('case_caseNumber')}) ---"
            )
            out(format_row(row))

    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
