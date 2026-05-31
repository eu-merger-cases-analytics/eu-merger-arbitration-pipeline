"""
Loads all merger decision PDF attachments from case-data-M.json
into the raw.decisions table in PostgreSQL.

Dynamic schema: scans all JSON keys across all nesting levels and
automatically adds missing columns to the table (all as TEXT).

Each row = one unique PDF attachment catalogue entry.
Unique business key: (att_attachmentLink, att_metadataReference).
Column naming convention:
    case_*      — case metadata keys
    caseAtt_*   — caseAttachments metadata keys
    dec_*       — decision metadata keys
    att_*       — decisionAttachments metadata keys

On update:
  - New rows are inserted (ON CONFLICT DO NOTHING for new key pairs).
  - Existing rows are compared field by field; changed fields are updated and logged.
  - Key pairs present in the database but missing from JSON are marked isActive=FALSE.
  - lastCheckedAt is updated for every processed row.

Prerequisites:
    Run init/create_raw_schema.sql first to create the table.

Run:
    docker compose exec python python ingestion/load_decisions.py
"""

import json
import logging
import os
from pathlib import Path

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _SCRIPT_DIR.parent
PROJECT_ROOT = _SCRIPTS_DIR.parent

JSON_PATH = PROJECT_ROOT / "data" / "raw" / "case-data-M.json"

SCHEMA = "raw"
TABLE = "decisions"

# Internal columns — not from JSON, never compared or overwritten
INTERNAL_COLUMNS = {
    "decision_id", "isActive", "removedDetectedAt",
    "loadedAt", "pdfProcessedAt", "pdfProcessingError", "lastCheckedAt",
}


def get_connection():
    """Creates a database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def first(lst: list):
    """Returns the first element of a list, or None if empty."""
    return lst[0] if lst else None


def join_list(value, sep=" | ") -> str:
    """Joins a list to a string with separator."""
    if isinstance(value, list):
        return sep.join(str(v) for v in value if v is not None)
    return str(value) if value is not None else ""


def flatten_metadata(meta: dict, prefix: str) -> dict:
    """
    Flattens a metadata dict into prefixed key-value pairs.
    All list values are joined with ' | '.
    Keys get the given prefix (e.g. 'case_', 'dec_', 'att_').
    """
    result = {}
    for key, val in meta.items():
        col_name = f"{prefix}{key}"
        if isinstance(val, list):
            result[col_name] = join_list(val)
        else:
            result[col_name] = str(val) if val is not None else None
    return result


def attachment_key(att_meta: dict) -> tuple[str, str] | None:
    """Returns (attachmentLink, metadataReference) or None if either is missing."""
    link_list = att_meta.get("attachmentLink", [])
    link = first(link_list) if isinstance(link_list, list) else link_list
    ref_list = att_meta.get("metadataReference", [])
    meta_ref = first(ref_list) if isinstance(ref_list, list) else ref_list
    if not link or not meta_ref:
        return None
    return link, meta_ref


def row_key_label(link: str, meta_ref: str) -> str:
    """Formats the business key for log messages."""
    return f"{link} | {meta_ref}"


def collect_all_keys(data: dict) -> set[str]:
    """
    Scans all cases and collects every unique column name
    across all nesting levels (case, caseAttachments, decisions, decisionAttachments).
    """
    keys = set()
    for case in data.values():
        keys.update(flatten_metadata(case.get("metadata", {}), "case_").keys())
        for ca in case.get("caseAttachments", []):
            keys.update(flatten_metadata(ca.get("metadata", {}), "caseAtt_").keys())
        for dec in case.get("decisions", []):
            keys.update(flatten_metadata(dec.get("metadata", {}), "dec_").keys())
            for att in dec.get("decisionAttachments", []):
                keys.update(flatten_metadata(att.get("metadata", {}), "att_").keys())
    return keys


def get_table_columns(conn) -> set[str]:
    """Returns the set of existing column names in the table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
        """, (SCHEMA, TABLE))
        return {row[0] for row in cur.fetchall()}


def add_missing_columns(conn, json_keys: set[str], table_columns: set[str]) -> None:
    """Adds columns present in JSON but missing from the table (all as TEXT)."""
    missing = json_keys - table_columns - INTERNAL_COLUMNS
    if not missing:
        return
    log.info("Adding %d new column(s) to %s.%s: %s", len(missing), SCHEMA, TABLE, sorted(missing))
    with conn.cursor() as cur:
        for col in sorted(missing):
            cur.execute(
                f'ALTER TABLE {SCHEMA}.{TABLE} ADD COLUMN IF NOT EXISTS "{col}" TEXT'
            )
    conn.commit()


def build_row(case_meta: dict, case_att_meta: dict,
              dec_meta: dict, att_meta: dict) -> dict:
    """Builds a flat row dict from all metadata levels."""
    row = {}
    row.update(flatten_metadata(case_meta, "case_"))
    row.update(flatten_metadata(case_att_meta, "caseAtt_"))
    row.update(flatten_metadata(dec_meta, "dec_"))
    row.update(flatten_metadata(att_meta, "att_"))
    return row


def get_existing_row(conn, link: str, meta_ref: str, columns: list[str]) -> dict | None:
    """Fetches an existing row from the database by business key."""
    col_list = ", ".join(f'"{c}"' for c in columns)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            f'SELECT {col_list} FROM {SCHEMA}.{TABLE} '
            f'WHERE "att_attachmentLink" = %s AND "att_metadataReference" = %s',
            (link, meta_ref),
        )
        row = cur.fetchone()
    return dict(row) if row else None


def compare_and_update(conn, new_row: dict, existing_row: dict,
                       data_columns: list[str], link: str, meta_ref: str) -> None:
    """
    Compares new JSON row with existing database row field by field.
    Updates changed fields and logs additions and removals.
    """
    key_label = row_key_label(link, meta_ref)
    changed = {}
    for col in data_columns:
        new_val = new_row.get(col)
        old_val = existing_row.get(col)
        # Normalise empty string and None as equivalent
        new_norm = new_val if new_val else None
        old_norm = old_val if old_val else None
        if new_norm != old_norm:
            changed[col] = (old_norm, new_norm)
            if old_norm and not new_norm:
                log.warning("Field removed [%s] %s: '%s' -> NULL", key_label, col, old_norm)
            elif not old_norm and new_norm:
                log.info("Field added [%s] %s: NULL -> '%s'", key_label, col, new_norm)
            else:
                log.info("Field changed [%s] %s: '%s' -> '%s'", key_label, col, old_norm, new_norm)

    if changed:
        set_clause = ", ".join(f'"{col}" = %s' for col in changed)
        values = [new_norm for _, new_norm in changed.values()]
        values.extend([link, meta_ref])
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE {SCHEMA}.{TABLE} SET {set_clause}, "lastCheckedAt" = NOW() '
                f'WHERE "att_attachmentLink" = %s AND "att_metadataReference" = %s',
                values,
            )
        conn.commit()
    else:
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE {SCHEMA}.{TABLE} SET "lastCheckedAt" = NOW() '
                f'WHERE "att_attachmentLink" = %s AND "att_metadataReference" = %s',
                (link, meta_ref),
            )
        conn.commit()


def insert_row(conn, row: dict, data_columns: list[str]) -> None:
    """Inserts a new row into the table."""
    col_list = ", ".join(f'"{c}"' for c in data_columns)
    placeholders = ", ".join(["%s"] * len(data_columns))
    values = [row.get(col) for col in data_columns]
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO {SCHEMA}.{TABLE} ({col_list}, "lastCheckedAt") '
            f'VALUES ({placeholders}, NOW()) '
            f'ON CONFLICT ("att_attachmentLink", "att_metadataReference") DO NOTHING',
            values,
        )
    conn.commit()


def mark_removed(conn, current_keys: set[tuple[str, str]]) -> int:
    """Marks rows as inactive if their business key is no longer in the JSON."""
    if not current_keys:
        raise RuntimeError(
            "No attachment keys found in JSON — aborting to prevent mass deactivation."
        )
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE _current_keys (
                link TEXT NOT NULL,
                meta_ref TEXT NOT NULL,
                PRIMARY KEY (link, meta_ref)
            ) ON COMMIT DROP;
        """)
        psycopg2.extras.execute_values(
            cur,
            "INSERT INTO _current_keys (link, meta_ref) VALUES %s",
            list(current_keys),
            page_size=1000,
        )
        cur.execute(f"""
            UPDATE {SCHEMA}.{TABLE} AS d
            SET "isActive" = FALSE, "removedDetectedAt" = NOW()
            WHERE d."isActive" = TRUE
            AND NOT EXISTS (
                SELECT 1 FROM _current_keys k
                WHERE k.link = d."att_attachmentLink"
                  AND k.meta_ref = d."att_metadataReference"
            )
        """)
        removed = cur.rowcount
    conn.commit()
    if removed > 0:
        log.warning("%d attachment row(s) marked as removed — missing from current JSON.", removed)
    return removed


def main() -> None:
    if not JSON_PATH.exists():
        raise FileNotFoundError(
            f"JSON file not found: {JSON_PATH}\n"
            "Run first: python ingestion/download_json.py"
        )

    log.info("Reading JSON from %s", JSON_PATH)
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    log.info("Total cases in JSON: %d", len(data))

    conn = get_connection()
    try:
        # 1. Collect all JSON keys and add missing columns dynamically
        log.info("Scanning all JSON keys...")
        json_keys = collect_all_keys(data)
        log.info("Unique keys found across all nesting levels: %d", len(json_keys))

        table_columns = get_table_columns(conn)
        add_missing_columns(conn, json_keys, table_columns)

        # Refresh column list after potential ALTER TABLE
        table_columns = get_table_columns(conn)
        data_columns = sorted(json_keys & table_columns)

        # 2. Process each attachment row
        current_keys: set[tuple[str, str]] = set()
        inserted = 0
        updated = 0
        skipped = 0

        for case_key, case in data.items():
            case_meta = case.get("metadata", {})

            # Case-level attachment metadata (usually empty)
            case_att_meta: dict = {}
            for ca in case.get("caseAttachments", []):
                case_att_meta.update(ca.get("metadata", {}))

            for dec in case.get("decisions", []):
                dec_meta = dec.get("metadata", {})

                for att in dec.get("decisionAttachments", []):
                    att_meta = att.get("metadata", {})
                    key = attachment_key(att_meta)
                    if key is None:
                        skipped += 1
                        continue

                    link, meta_ref = key
                    current_keys.add(key)
                    new_row = build_row(case_meta, case_att_meta, dec_meta, att_meta)

                    existing = get_existing_row(conn, link, meta_ref, data_columns)
                    if existing is None:
                        insert_row(conn, new_row, data_columns)
                        inserted += 1
                    else:
                        compare_and_update(conn, new_row, existing, data_columns, link, meta_ref)
                        updated += 1

        log.info("Inserted: %d  |  Checked/updated: %d  |  Skipped (missing key): %d",
                 inserted, updated, skipped)

        # 3. Mark removed
        removed = mark_removed(conn, current_keys)
        log.info("Marked as removed: %d", removed)

    finally:
        conn.close()

    log.info("Done.")


if __name__ == "__main__":
    main()
