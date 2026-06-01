"""
Exports all rows from raw.decision_hits to a readable JSON file in data/processed/.

Run:
    docker compose exec python python analysis/export_decision_hits_json.py
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
OUTPUT_PATH = _PROJECT_ROOT / "data" / "processed" / "decision_hits.json"

SCHEMA = "raw"
TABLE = "decision_hits"

EXPORT_COLUMNS = [
    "case_caseNumber",
    "case_caseCompanies",
    "att_attachmentLink",
    "matchedLanguage",
    "matchedKeywords",
    "matchContext",
    "dec_decisionAdoptionDate",
    "case_caseSectors",
]


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def fetch_hits(conn) -> list[dict]:
    col_list = ", ".join(f'"{c}"' for c in EXPORT_COLUMNS)
    sql = f"""
        SELECT {col_list}
        FROM {SCHEMA}.{TABLE}
        ORDER BY "hit_id"
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        rows = []
        for row in cur.fetchall():
            record = {col: row[col] for col in EXPORT_COLUMNS}
            rows.append(record)
        return rows


def main() -> None:
    conn = get_connection()
    try:
        hits = fetch_hits(conn)
    finally:
        conn.close()

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": f"{SCHEMA}.{TABLE}",
        "rowCount": len(hits),
        "columns": EXPORT_COLUMNS,
        "hits": hits,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Exported {len(hits)} hit(s) to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
