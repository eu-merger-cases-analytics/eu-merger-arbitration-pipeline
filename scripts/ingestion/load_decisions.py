"""
Loads all merger decision PDF attachments and other selected metadata from case-data-M.json
into the raw.decisions table in PostgreSQL.
 
Each row = one unique PDF attachment (attachmentLink is the primary key).
Case and decision fields repeat for each attachment row.
 
On update:
  - New attachmentLinks are inserted.
  - Existing attachmentLinks are skipped (ON CONFLICT DO NOTHING).
  - AttachmentLinks present in the database but missing from the new JSON
    are marked isActive=FALSE with a removedDetectedAt timestamp.
 
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
from psycopg2.extras import execute_values
 
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
 
# Fields required at each level — used to detect schema changes in source data
REQUIRED_CASE_KEYS = {
    "caseNumber", "caseTitle", "caseCompanies", "caseInstrument",
    "caseRegulation", "caseSimplified", "caseSectors", "caseInitiationDate",
    "caseNotificationDate", "caseDeadlineDate", "caseLastDecisionDate",
}
REQUIRED_DECISION_KEYS = {
    "decisionNumber", "decisionAdoptionDate",
    "decisionOfficialJournalPublicationsPublishedDates", "decisionTypes",
}
REQUIRED_ATTACHMENT_KEYS = {
    "attachmentLink", "attachmentLanguage", "attachmentName", "language",
    "metadataReference",
}
 
COLUMNS = [
    "caseNumber",
    "caseTitle",
    "caseCompanies",
    "caseInstrument",
    "caseRegulation",
    "caseSimplified",
    "caseSectors",
    "caseInitiationDate",
    "caseNotificationDate",
    "caseDeadlineDate",
    "caseLastDecisionDate",
    "caseAttachments",
    "decisionNumber",
    "decisionAdoptionDate",
    "decisionOfficialJournalPublicationsPublishedDates",
    "decisionTypeCode",
    "decisionTypeLabel",
    "attachmentMetadataReference",
    "attachmentLanguage",
    "attachmentLanguageLower",
    "attachmentName",
    "attachmentLink",
]
 
 
def get_connection():
    """Creates a database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )
 
 
def first(lst: list) -> object:
    """Returns the first element of a list, or None if empty."""
    return lst[0] if lst else None
 
 
def parse_label(raw: str) -> str:
    """Parses a JSON-encoded label string, falls back to raw value."""
    try:
        return json.loads(raw).get("label", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw
 
 
def safe_json_get(raw: str, key: str):
    """Safely extracts a key from a JSON-encoded string, returns None on failure."""
    try:
        return json.loads(raw).get(key)
    except (json.JSONDecodeError, AttributeError):
        return None
 
 
def join_list(value, sep=" | ") -> str:
    """Joins a list to a string with separator."""
    if isinstance(value, list):
        return sep.join(str(v) for v in value if v)
    return value or ""
 
 
def check_missing_keys(meta: dict, required: set, context: str) -> set:
    """Returns missing keys from a metadata dict. Logs a warning if any found."""
    missing = required - set(meta.keys())
    if missing:
        log.warning("Missing keys in %s: %s", context, missing)
    return missing
 
 
def build_rows(data: dict) -> tuple[list[tuple], set[str]]:
    """
    Builds rows for insertion and collects all attachment URLs seen in JSON.
    Returns (rows, all_attachment_links).
    """
    rows = []
    all_links = set()
    missing_key_count = 0
 
    for case_key, case in data.items():
        case_meta = case.get("metadata", {})
 
        # Check for schema changes in source data
        missing = check_missing_keys(case_meta, REQUIRED_CASE_KEYS, f"case {case_key}")
        if missing:
            missing_key_count += 1
 
        case_number = first(case_meta.get("caseNumber", []))
        case_companies = join_list(case_meta.get("caseCompanies", []))
        case_sectors = join_list(
            [parse_label(s) for s in case_meta.get("caseSectors", [])]
        )
        case_attachments = join_list(
            [first(ca.get("metadata", {}).get("metadataReference", []))
             for ca in case.get("caseAttachments", [])]
        )
 
        for dec in case.get("decisions", []):
            dec_meta = dec.get("metadata", {})
            if check_missing_keys(dec_meta, REQUIRED_DECISION_KEYS, f"decision in {case_key}"):
                missing_key_count += 1
 
            dec_types = dec_meta.get("decisionTypes", [])
            # Join all decision types — a decision may have multiple types
            dec_type_code = " | ".join(
                safe_json_get(t, "code") or "" for t in dec_types
            ) or None
            dec_type_label = " | ".join(
                parse_label(t) for t in dec_types
            ) or None
 
            oj_dates = join_list(
                dec_meta.get("decisionOfficialJournalPublicationsPublishedDates", [])
            )
 
            for att in dec.get("decisionAttachments", []):
                att_meta = att.get("metadata", {})
                if check_missing_keys(
                    att_meta, REQUIRED_ATTACHMENT_KEYS,
                    f"attachment in {case_key}"
                ):
                    missing_key_count += 1
 
                link = first(att_meta.get("attachmentLink", []))
                if not link:
                    continue
 
                all_links.add(link)
 
                rows.append(tuple([
                    case_number,
                    first(case_meta.get("caseTitle", [])),
                    case_companies,
                    first(case_meta.get("caseInstrument", [])),
                    first(case_meta.get("caseRegulation", [])),
                    first(case_meta.get("caseSimplified", [])),
                    case_sectors,
                    first(case_meta.get("caseInitiationDate", [])),
                    first(case_meta.get("caseNotificationDate", [])),
                    first(case_meta.get("caseDeadlineDate", [])),
                    first(case_meta.get("caseLastDecisionDate", [])),
                    case_attachments,
                    first(dec_meta.get("decisionNumber", [])),
                    first(dec_meta.get("decisionAdoptionDate", [])),
                    oj_dates,
                    dec_type_code,
                    dec_type_label,
                    first(att_meta.get("metadataReference", [])),
                    first(att_meta.get("attachmentLanguage", [])),
                    first(att_meta.get("language", [])),
                    first(att_meta.get("attachmentName", [])),
                    link,
                ]))
 
    if missing_key_count > 0:
        log.warning(
            "%d case(s) had missing keys — possible schema change in source data. "
            "Check logs above for decision and attachment level warnings.",
            missing_key_count,
        )
 
    return rows, all_links
 
 
def insert_new_rows(conn, rows: list[tuple]) -> int:
    """Inserts new rows, skipping existing attachmentLinks (ON CONFLICT DO NOTHING)."""
    if not rows:
        return 0
 
    column_list = ", ".join(f'"{col}"' for col in COLUMNS)
    insert_sql = (
        f"INSERT INTO {SCHEMA}.{TABLE} ({column_list}) VALUES %s "
        f'ON CONFLICT ("attachmentLink") DO NOTHING'
    )
 
    with conn.cursor() as cur:
        execute_values(cur, insert_sql, rows, page_size=1000)
        inserted = cur.rowcount
 
    return inserted
 
 
def mark_removed(conn, all_links: set[str]) -> int:
    """
    Marks rows as inactive if their attachmentLink is no longer in the source JSON.
    Returns the number of rows marked as removed.
    """
    if not all_links:
        raise RuntimeError(
            "No attachment links found in JSON — aborting mark_removed to prevent "
            "mass deactivation. Check JSON parsing and source data."
        )
 
    with conn.cursor() as cur:
        # Create a temporary table with all current links
        cur.execute("CREATE TEMP TABLE _current_links (link TEXT PRIMARY KEY) ON COMMIT DROP;")
        execute_values(cur, "INSERT INTO _current_links (link) VALUES %s",
                       [(lnk,) for lnk in all_links], page_size=1000)
 
        # Mark removed
        cur.execute(f"""
            UPDATE {SCHEMA}.{TABLE}
            SET "isActive" = FALSE,
                "removedDetectedAt" = NOW()
            WHERE "attachmentLink" NOT IN (SELECT link FROM _current_links)
            AND "isActive" = TRUE
        """)
        removed = cur.rowcount
 
    if removed > 0:
        log.warning(
            "%d PDF attachment(s) marked as removed — present in database but missing from JSON. "
            "This may indicate a schema change or data quality issue in the source.",
            removed,
        )
 
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
 
    log.info("Building rows...")
    rows, all_links = build_rows(data)
    log.info("Total attachment rows to process: %d", len(rows))
 
    conn = get_connection()
    try:
        with conn:  # transaction — rolls back on error
            inserted = insert_new_rows(conn, rows)
            removed = mark_removed(conn, all_links)
 
        log.info("New rows inserted: %d", inserted)
        log.info("Rows marked as removed: %d", removed)
    finally:
        conn.close()
 
    log.info("Done.")
 
 
if __name__ == "__main__":
    main()
 