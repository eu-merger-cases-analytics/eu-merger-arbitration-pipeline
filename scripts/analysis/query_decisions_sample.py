"""
Fetches the first row from raw.decisions and writes output to
query_decisions_sample_output.txt (overwrites on each run).

Run:
    docker compose exec python python analysis/query_decisions_sample.py
"""

import json
from io import StringIO
from pathlib import Path

import psycopg2
import psycopg2.extras

OUTPUT_PATH = Path(__file__).resolve().parent / "query_decisions_sample_output.txt"

SCHEMA = "raw"
TABLE = "decisions"


def get_connection():
    """Creates a database connection from environment variables."""
    import os

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def fetch_sample_row(conn) -> dict | None:
    """Returns the first row inserted into raw.decisions (lowest decision_id)."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f'SELECT * FROM {SCHEMA}.{TABLE} '
            f'ORDER BY "decision_id" LIMIT 1'
        )
        row = cur.fetchone()
        return dict(row) if row else None


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

    def out(text=""):
        print(text)
        buf.write(text + "\n")

    conn = get_connection()
    try:
        row = fetch_sample_row(conn)
    finally:
        conn.close()

    if row is None:
        out(f"No rows found in {SCHEMA}.{TABLE}.")
        out("Run first: python ingestion/load_decisions.py")
    else:
        out(
            f"First saved row from {SCHEMA}.{TABLE} "
            f'(decision_id={row.get("decision_id")}, case={row.get("case_caseNumber")}):'
        )
        out()
        out(format_row(row))

    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
