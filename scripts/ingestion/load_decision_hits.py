"""
Reads PDF attachments from raw.decisions, searches for arbitration keywords,
and writes rows with matches to raw.decision_hits.

Workflow per row (isActive = TRUE, pdfProcessedAt IS NULL):
  1. Download PDF from att_attachmentLink
  2. Extract text and match keywords for att_attachmentLanguage (config/keywords.txt)
  3. On match: copy metadata columns from raw.decisions into raw.decision_hits
  4. Always set raw.decisions.pdfProcessedAt = NOW() (including failed downloads)

Prerequisites:
    init/create_raw_schema.sql, load_decisions.py,
    init/create_raw_decision_hits.sql

Run:
    docker compose exec python python ingestion/load_decision_hits.py

Optional:
    TEST_LIMIT=10 docker compose exec python python ingestion/load_decision_hits.py
    RETRY_DOWNLOAD_ERRORS=1 docker compose exec python python ingestion/load_decision_hits.py
    REQUEST_DELAY_SECONDS=2 docker compose exec -e REQUEST_DELAY_SECONDS=2 python python ingestion/load_decision_hits.py
"""

import io
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pdfplumber
import psycopg2
import psycopg2.extras
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

_SCRIPT_DIR = Path(__file__).resolve().parent
_SCRIPTS_DIR = _SCRIPT_DIR.parent
PROJECT_ROOT = _SCRIPTS_DIR.parent

SCHEMA = "raw"
DECISIONS_TABLE = "decisions"
HITS_TABLE = "decision_hits"

KEYWORDS_PATHS = [
    Path("/config/keywords.txt"),
    PROJECT_ROOT / "config" / "keywords.txt",
]

# Columns on raw.decisions that are not copied to raw.decision_hits
DECISIONS_INTERNAL_COLUMNS = {
    "decision_id",
    "isActive",
    "removedDetectedAt",
    "loadedAt",
    "pdfProcessedAt",
    "pdfProcessingError",
    "lastCheckedAt",
}

# Columns defined in create_raw_decision_hits.sql (not copied from decisions)
HITS_FIXED_COLUMNS = {
    "hit_id",
    "decision_id",
    "att_attachmentLink",
    "att_metadataReference",
    "matchedKeywords",
    "matchedLanguage",
    "matchContext",
    "loadedAt",
}

CONTEXT_CHARS = 100
REQUEST_TIMEOUT = 120
REQUEST_DELAY_SECONDS = float(os.environ.get("REQUEST_DELAY_SECONDS", "1.5"))
USER_AGENT = (
    "eu-merger-arbitration-pipeline/1.0 "
    "(research; +https://github.com/)"
)


def format_duration(seconds: float) -> str:
    """Formats elapsed seconds for log messages."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}m {seconds % 60:.0f}s"
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{hours}h {minutes}m {seconds % 60:.0f}s"


def build_http_session() -> requests.Session:
    """Session with retries, backoff, and a browser-like User-Agent."""
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,*/*",
        }
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


@dataclass
class MatchResult:
    keywords: list[str]
    language: str
    context: str
    position: int


def get_connection():
    """Creates a database connection from environment variables."""
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def resolve_keywords_path() -> Path:
    for path in KEYWORDS_PATHS:
        if path.exists():
            return path
    raise FileNotFoundError(
        "keywords.txt not found. Expected one of: "
        + ", ".join(str(p) for p in KEYWORDS_PATHS)
    )


def load_keywords(path: Path) -> dict[str, list[list[str]]]:
    """
    Parses keywords.txt into {LANG: [[term or AND group], ...]}.
    AND groups use colon-separated parts after the language prefix (e.g. CZ: a*:b*).
    """
    rules: dict[str, list[list[str]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            log.warning("Skipping invalid keyword line (no colon): %s", line)
            continue
        lang, rest = line.split(":", 1)
        lang = lang.strip().upper()
        patterns = [part.strip() for part in rest.split(":") if part.strip()]
        if not lang or not patterns:
            continue
        rules.setdefault(lang, []).append(patterns)
    return rules


def pattern_to_regex(pattern: str) -> re.Pattern[str]:
    """Turns a keyword pattern with * wildcards into a case-insensitive regex."""
    parts = []
    for char in pattern:
        parts.append(".*" if char == "*" else re.escape(char))
    return re.compile("".join(parts), re.IGNORECASE | re.UNICODE)


def find_matches(text: str, rule_groups: list[list[str]]) -> list[tuple[str, int]]:
    """Returns (rule_label, earliest_match_position) for each matching rule group."""
    hits: list[tuple[str, int]] = []
    for patterns in rule_groups:
        positions: list[int] = []
        labels: list[str] = []
        for pattern in patterns:
            match = pattern_to_regex(pattern).search(text)
            if not match:
                break
            positions.append(match.start())
            labels.append(pattern)
        else:
            label = ":".join(labels) if len(labels) > 1 else labels[0]
            hits.append((label, min(positions)))
    return hits


def extract_context(text: str, position: int) -> str:
    """Returns ~100 characters of text centred on the match position."""
    start = max(0, position - CONTEXT_CHARS)
    end = min(len(text), position + CONTEXT_CHARS)
    snippet = text[start:end].strip()
    return " ".join(snippet.split())


def attachment_language(row: dict) -> str | None:
    """Reads attachment language from row (att_attachmentLanguage preferred)."""
    for col in ("att_attachmentLanguage", "att_language"):
        value = row.get(col)
        if value and str(value).strip():
            return str(value).strip().upper()
    return None


def download_pdf(session: requests.Session, url: str) -> bytes:
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def extract_pdf_text(pdf_bytes: bytes) -> str:
    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                parts.append(page_text)
    return "\n".join(parts)


def get_table_columns(conn, table: str) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (SCHEMA, table),
        )
        return {row[0] for row in cur.fetchall()}


def add_missing_columns(conn, columns: set[str], table: str, exclude: set[str]) -> None:
    """Adds TEXT columns present in decisions metadata but missing from decision_hits."""
    existing = get_table_columns(conn, table)
    missing = columns - existing - exclude
    if not missing:
        return
    log.info(
        "Adding %d column(s) to %s.%s: %s",
        len(missing), SCHEMA, table, sorted(missing),
    )
    with conn.cursor() as cur:
        for col in sorted(missing):
            cur.execute(
                f'ALTER TABLE {SCHEMA}.{HITS_TABLE} '
                f'ADD COLUMN IF NOT EXISTS "{col}" TEXT'
            )
    conn.commit()


def fetch_pending_rows(
    conn,
    limit: int | None,
    *,
    retry_download_errors: bool = False,
) -> list[dict]:
    if retry_download_errors:
        where = (
            '"isActive" = TRUE AND "pdfProcessingError" LIKE \'download:%%\''
        )
    else:
        where = '"isActive" = TRUE AND "pdfProcessedAt" IS NULL'
    sql = f"""
        SELECT * FROM {SCHEMA}.{DECISIONS_TABLE}
        WHERE {where}
        ORDER BY "decision_id"
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(row) for row in cur.fetchall()]


def ensure_processing_error_column(conn) -> None:
    """Adds pdfProcessingError on existing databases created before the column existed."""
    with conn.cursor() as cur:
        cur.execute(
            f'ALTER TABLE {SCHEMA}.{DECISIONS_TABLE} '
            f'ADD COLUMN IF NOT EXISTS "pdfProcessingError" TEXT'
        )
    conn.commit()


def mark_pdf_processed(conn, decision_id: int, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            f'UPDATE {SCHEMA}.{DECISIONS_TABLE} '
            f'SET "pdfProcessedAt" = NOW(), "pdfProcessingError" = %s '
            f'WHERE "decision_id" = %s',
            (error, decision_id),
        )
    conn.commit()


def insert_hit(
    conn,
    row: dict,
    match: MatchResult,
    copy_columns: list[str],
) -> None:
    columns = (
        ["decision_id", "att_attachmentLink", "att_metadataReference"]
        + copy_columns
        + ["matchedKeywords", "matchedLanguage", "matchContext"]
    )
    values = [
        row["decision_id"],
        row["att_attachmentLink"],
        row["att_metadataReference"],
        *[row.get(col) for col in copy_columns],
        " | ".join(match.keywords),
        match.language,
        match.context,
    ]
    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join(["%s"] * len(columns))
    update_set = ", ".join(
        f'"{c}" = EXCLUDED."{c}"'
        for c in copy_columns
        + ["matchedKeywords", "matchedLanguage", "matchContext"]
    )
    with conn.cursor() as cur:
        cur.execute(
            f'INSERT INTO {SCHEMA}.{HITS_TABLE} ({col_list}, "loadedAt") '
            f"VALUES ({placeholders}, NOW()) "
            f'ON CONFLICT ("att_attachmentLink", "att_metadataReference") DO UPDATE '
            f"SET {update_set}, \"loadedAt\" = NOW()",
            values,
        )
    conn.commit()


def process_row(
    row: dict,
    keywords_by_lang: dict[str, list[list[str]]],
    session: requests.Session,
) -> MatchResult | None:
    decision_id = row["decision_id"]
    link = row["att_attachmentLink"]
    lang = attachment_language(row)

    if not lang:
        log.warning("[%s] No att_attachmentLanguage — skipping keyword search", decision_id)
        return None

    rules = keywords_by_lang.get(lang)
    if not rules:
        log.debug("[%s] No keyword rules for language %s", decision_id, lang)
        return None

    log.info("[%s] Downloading PDF: %s", decision_id, link)
    pdf_bytes = download_pdf(session, link)
    text = extract_pdf_text(pdf_bytes)
    if not text.strip():
        log.warning("[%s] No extractable text in PDF", decision_id)
        return None

    matches = find_matches(text, rules)
    if not matches:
        return None

    keywords = [label for label, _ in matches]
    position = min(pos for _, pos in matches)
    context = extract_context(text, position)
    return MatchResult(keywords=keywords, language=lang, context=context, position=position)


def main() -> None:
    keywords_path = resolve_keywords_path()
    keywords_by_lang = load_keywords(keywords_path)
    log.info("Loaded keyword rules for %d language(s) from %s", len(keywords_by_lang), keywords_path)

    test_limit = os.environ.get("TEST_LIMIT")
    limit = int(test_limit) if test_limit else None
    if limit is not None:
        log.info("TEST_LIMIT=%d — processing at most %d row(s)", limit, limit)

    retry_download_errors = os.environ.get("RETRY_DOWNLOAD_ERRORS", "").lower() in {
        "1", "true", "yes",
    }
    if retry_download_errors:
        log.info("RETRY_DOWNLOAD_ERRORS — re-processing rows with download failures only")

    log.info(
        "Download pacing: REQUEST_DELAY_SECONDS=%.1f, REQUEST_TIMEOUT=%d",
        REQUEST_DELAY_SECONDS,
        REQUEST_TIMEOUT,
    )

    session = build_http_session()
    conn = get_connection()
    hits_inserted = 0
    processed = 0
    errors = 0

    try:
        decisions_columns = get_table_columns(conn, DECISIONS_TABLE)
        copy_columns = sorted(
            decisions_columns - DECISIONS_INTERNAL_COLUMNS - HITS_FIXED_COLUMNS
        )
        add_missing_columns(conn, set(copy_columns), HITS_TABLE, HITS_FIXED_COLUMNS)
        ensure_processing_error_column(conn)

        rows = fetch_pending_rows(
            conn, limit, retry_download_errors=retry_download_errors
        )
        log.info("Found %d row(s) to process", len(rows))

        run_started = time.perf_counter()
        row_elapsed_sum = 0.0

        for row in rows:
            decision_id = row["decision_id"]
            row_started = time.perf_counter()
            error_msg: str | None = None
            try:
                match = process_row(row, keywords_by_lang, session)
                if match:
                    insert_hit(conn, row, match, copy_columns)
                    hits_inserted += 1
                    log.info(
                        "[%s] Hit: %s (%s)",
                        decision_id,
                        " | ".join(match.keywords),
                        match.language,
                    )
            except requests.RequestException as exc:
                errors += 1
                error_msg = f"download: {exc}"
                log.error("[%s] PDF download failed: %s", decision_id, exc)
            except Exception as exc:
                errors += 1
                error_msg = f"processing: {exc}"
                log.exception("[%s] Processing failed: %s", decision_id, exc)
            finally:
                mark_pdf_processed(conn, decision_id, error_msg)
                processed += 1
                row_elapsed = time.perf_counter() - row_started
                row_elapsed_sum += row_elapsed
                log.debug("[%s] Row finished in %.2fs", decision_id, row_elapsed)
                if REQUEST_DELAY_SECONDS > 0:
                    time.sleep(REQUEST_DELAY_SECONDS)

        run_elapsed = time.perf_counter() - run_started
        if processed:
            avg_row = row_elapsed_sum / processed
            log.info(
                "Processing time: %s wall clock | %.2fs avg per row (excl. REQUEST_DELAY_SECONDS) | %.1fs delay between rows",
                format_duration(run_elapsed),
                avg_row,
                REQUEST_DELAY_SECONDS,
            )

    finally:
        session.close()
        conn.close()

    log.info(
        "Done. Processed: %d  |  Hits saved: %d  |  Errors: %d",
        processed,
        hits_inserted,
        errors,
    )


if __name__ == "__main__":
    main()
