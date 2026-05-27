"""
Loads arbitration_hits.jsonl into PostgreSQL table staging.arbitration_hits.
 
Each row = one match (one keyword found in one PDF).
Case and decision fields repeat for each match row.
 
Prerequisites:
    Run init/create_staging_schema.sql first to create the table.
 
Run:
    docker compose exec python python ingestion/load_hits_to_db.py
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
 
HITS_PATH = PROJECT_ROOT / "data" / "processed" / "arbitration_hits.jsonl"
 
TABLE = "arbitration_hits"
SCHEMA = "staging"
 
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
    "attachmentName",
    "attachmentLink",
    "matchKeyword",
    "matchLanguage",
    "matchContext",
    "processedAt",
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
 
 
def join_list(value, sep=" | "):
    """Joins a list to a string with separator. Returns value as-is if not a list."""
    if isinstance(value, list):
        return sep.join(str(v) for v in value if v)
    return value or ""
 
 
def build_rows(hits: list[dict]) -> list[tuple]:
    """
    Flattens hits into rows. One row per keyword match per case.
    For each match, finds the corresponding attachment by PDF URL.
    """
    rows = []
 
    for hit in hits:
        case_companies = join_list(hit.get("caseCompanies"))
        case_sectors = join_list(hit.get("caseSectors"))
        case_attachments = join_list(
            [a.get("metadataReference", "") for a in hit.get("caseAttachments", [])]
        )
 
        for match in hit.get("_matches", []):
            dec_idx = match.get("dec_idx", 0)
            decisions = hit.get("decisions", [])
            dec = decisions[dec_idx] if dec_idx < len(decisions) else {}
 
            dec_types = dec.get("decisionTypes", [])
            dec_type = dec_types[0] if dec_types else {}
 
            oj_dates = join_list(
                dec.get("decisionOfficialJournalPublicationsPublishedDates", [])
            )
 
            pdf_url = match.get("pdfUrl", "")
            matched_att = next(
                (
                    att for att in dec.get("decisionAttachments", [])
                    if att.get("attachmentLink") == pdf_url
                ),
                {},
            )
 
            for kw in match.get("keywords", []):
                rows.append(tuple([
                    hit.get("caseNumber"),
                    hit.get("caseTitle"),
                    case_companies,
                    hit.get("caseInstrument"),
                    hit.get("caseRegulation"),
                    hit.get("caseSimplified"),
                    case_sectors,
                    hit.get("caseInitiationDate"),
                    hit.get("caseNotificationDate"),
                    hit.get("caseDeadlineDate"),
                    hit.get("caseLastDecisionDate"),
                    case_attachments,
                    dec.get("decisionNumber"),
                    dec.get("decisionAdoptionDate"),
                    oj_dates,
                    dec_type.get("code"),
                    dec_type.get("label"),
                    matched_att.get("metadataReference"),
                    matched_att.get("attachmentLanguage"),
                    matched_att.get("attachmentName"),
                    pdf_url,
                    kw.get("keyword"),
                    kw.get("language"),
                    kw.get("context"),
                    hit.get("_processedAt"),
                ]))
 
    return rows
 
 
def load(conn, rows: list[tuple]) -> None:
    """Truncates and reloads the table with fresh data."""
    if not rows:
        log.warning("No rows to load.")
        return
 
    column_list = ", ".join(f'"{col}"' for col in COLUMNS)
    insert_sql = f"INSERT INTO {SCHEMA}.{TABLE} ({column_list}) VALUES %s"
 
    with conn.cursor() as cur:
        cur.execute(f'TRUNCATE TABLE {SCHEMA}."{TABLE}";')
        execute_values(cur, insert_sql, rows, page_size=500)
 
    conn.commit()
    log.info("Loaded %d rows into %s.%s", len(rows), SCHEMA, TABLE)
 
 
def main() -> None:
    if not HITS_PATH.exists():
        raise FileNotFoundError(
            f"Hits file not found: {HITS_PATH}\n"
            "Run first: python ingestion/ingest.py"
        )
 
    log.info("Reading hits from %s", HITS_PATH)
    hits = []
    with open(HITS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hits.append(json.loads(line))
    log.info("Loaded %d hit records", len(hits))
 
    rows = build_rows(hits)
    log.info("Built %d rows (one per keyword match)", len(rows))
 
    conn = get_connection()
    try:
        load(conn, rows)
    finally:
        conn.close()
 
    log.info("Done.")
 
 
if __name__ == "__main__":
    main()