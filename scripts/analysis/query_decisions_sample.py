"""
Fetches all rows from raw.decisions for case_caseNumber M.409 and writes
output to query_decisions_sample_output.txt (overwrites on each run).

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
CASE_NUMBER = "M.409"


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


def fetch_rows(conn, case_number: str) -> list[dict]:
    """Returns all rows from raw.decisions where case_caseNumber matches."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f'SELECT * FROM {SCHEMA}.{TABLE} '
            f'WHERE "case_caseNumber" = %s ORDER BY "decision_id"',
            (case_number,),
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

    def out(text=""):
        print(text)
        buf.write(text + "\n")

    conn = get_connection()
    try:
        rows = fetch_rows(conn, case_number=CASE_NUMBER)
    finally:
        conn.close()

    if not rows:
        out(f'No rows found for case_caseNumber = "{CASE_NUMBER}".')
        out("Run first: python ingestion/load_decisions.py")
    else:
        out(f'All rows from raw.decisions where case_caseNumber = "{CASE_NUMBER}": {len(rows)}')
        for i, row in enumerate(rows, 1):
            out()
            out(f"--- Row {i} ---")
            out(format_row(row))

    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
