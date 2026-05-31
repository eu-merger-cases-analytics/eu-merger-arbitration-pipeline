"""
Lists all date-like fields at case, decision, and attachment levels and counts
how many entities have a non-empty value.

Reads:
  - data/raw/case-data-M.json (hierarchical counts by metadata level)
  - raw.decisions in PostgreSQL (flattened column counts)

Outputs (overwritten on each run):
  - summarize_date_fields_json_output.txt
  - summarize_date_fields_db_output.txt

Run:
    docker compose exec python python analysis/summarize_date_fields.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from io import StringIO
from pathlib import Path

import psycopg2

JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "case-data-M.json"
OUTPUT_DIR = Path(__file__).resolve().parent
JSON_OUTPUT = OUTPUT_DIR / "summarize_date_fields_json_output.txt"
DB_OUTPUT = OUTPUT_DIR / "summarize_date_fields_db_output.txt"

SEP = "=" * 72
DATE_FIELD_RE = re.compile(r"date", re.IGNORECASE)

ART6_SUBSTRING = "6(1)(b)"
ART8_SUBSTRING = "8(2)"

SCHEMA = "raw"
TABLE = "decisions"


def get_connection():
    import os

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def is_date_field(name: str) -> bool:
    return bool(DATE_FIELD_RE.search(name))


def parse_label(raw) -> str:
    try:
        return json.loads(raw).get("label", raw)
    except (json.JSONDecodeError, AttributeError, TypeError):
        return str(raw) if raw is not None else ""


def case_has_relevant_decision(case: dict) -> bool:
    for dec in case.get("decisions", []):
        for raw in dec.get("metadata", {}).get("decisionTypes", []):
            label = parse_label(raw)
            if ART6_SUBSTRING in label or ART8_SUBSTRING in label:
                return True
    return False


def metadata_has_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(metadata_has_value(item) for item in value)
    if isinstance(value, dict):
        return bool(value)
    text = str(value).strip()
    return text != "" and text.lower() != "none"


class LevelStats:
    def __init__(self) -> None:
        self.total = 0
        self.field_counts: dict[str, int] = defaultdict(int)
        self.all_fields: set[str] = set()

    def record(self, metadata: dict) -> None:
        self.total += 1
        for key, value in metadata.items():
            if not is_date_field(key):
                continue
            self.all_fields.add(key)
            if metadata_has_value(value):
                self.field_counts[key] += 1


def collect_json_stats(cases: list[dict]) -> tuple[LevelStats, LevelStats, LevelStats, LevelStats]:
    case_stats = LevelStats()
    case_att_stats = LevelStats()
    decision_stats = LevelStats()
    attachment_stats = LevelStats()

    for case in cases:
        case_stats.record(case.get("metadata", {}))
        for ca in case.get("caseAttachments", []):
            case_att_stats.record(ca.get("metadata", {}))
        for dec in case.get("decisions", []):
            decision_stats.record(dec.get("metadata", {}))
            for att in dec.get("decisionAttachments", []):
                attachment_stats.record(att.get("metadata", {}))

    return case_stats, case_att_stats, decision_stats, attachment_stats


def format_level_section(title: str, stats: LevelStats) -> list[str]:
    lines = [SEP, title, f"Entities: {stats.total}"]
    if stats.total == 0:
        lines.append("  (no entities)")
        return lines

    fields = sorted(stats.all_fields)
    if not fields:
        lines.append("  No date-like metadata fields found.")
        return lines

    col = max(len(f) for f in fields) + 2
    lines.append("")
    lines.append(f"  {'Field':<{col}} {'With value':>12} {'Empty':>12} {'Fill %':>8}")
    lines.append(f"  {'-' * col} {'-' * 12} {'-' * 12} {'-' * 8}")

    always_filled: list[str] = []
    for field in fields:
        with_value = stats.field_counts.get(field, 0)
        empty = stats.total - with_value
        pct = 100.0 * with_value / stats.total if stats.total else 0.0
        lines.append(
            f"  {field:<{col}} {with_value:>12,d} {empty:>12,d} {pct:>7.1f}%"
        )
        if with_value == stats.total:
            always_filled.append(field)

    lines.append("")
    if always_filled:
        lines.append("  Always filled (100%):")
        for field in always_filled:
            lines.append(f"    - {field}")
    else:
        lines.append("  Always filled (100%): none")

    return lines


def analyze_json(all_cases: list[dict], relevant_cases: list[dict]) -> str:
    buf = StringIO()

    def out(lines: list[str] | str = "") -> None:
        if isinstance(lines, str):
            buf.write(lines + "\n")
        else:
            for line in lines:
                buf.write(line + "\n")

    out("Date fields in case-data-M.json")
    out(f"Source: {JSON_PATH}")
    out("")
    out("A field counts as 'has value' when metadata is non-null and non-empty")
    out("(for list fields: at least one non-empty element).")
    out("")
    out("Date-like field = metadata key name contains 'date' (case-insensitive).")

    for label, cases in [
        ("ALL CASES", all_cases),
        ("RELEVANT CASES (Art. 6(1)(b) or 8(2) in decisionTypes)", relevant_cases),
    ]:
        case_s, case_att_s, dec_s, att_s = collect_json_stats(cases)
        out("")
        out(SEP)
        out(label)
        out(f"Cases in scope: {len(cases)}")
        for section_title, stats in [
            ("CASE metadata (case.metadata)", case_s),
            ("CASE ATTACHMENT metadata (caseAttachments[].metadata)", case_att_s),
            ("DECISION metadata (decisions[].metadata)", dec_s),
            ("DECISION ATTACHMENT metadata (decisionAttachments[].metadata)", att_s),
        ]:
            out("")
            out(format_level_section(section_title, stats))

    return buf.getvalue()


def analyze_json_main() -> str:
    if not JSON_PATH.exists():
        return (
            f"JSON file not found: {JSON_PATH}\n"
            "Run first: python ingestion/download_json.py"
        )

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    all_cases = list(data.values())
    relevant_cases = [c for c in all_cases if case_has_relevant_decision(c)]
    return analyze_json(all_cases, relevant_cases)


def db_level_from_column(column: str) -> str:
    if column.startswith("caseAtt_"):
        return "case_attachment"
    if column.startswith("case_"):
        return "case"
    if column.startswith("dec_"):
        return "decision"
    if column.startswith("att_"):
        return "decision_attachment"
    if column in {"pdfProcessedAt", "removedDetectedAt", "loadedAt", "lastCheckedAt"}:
        return "pipeline_tracking"
    return "other"


def analyze_db() -> str:
    buf = StringIO()

    def out(text: str = "") -> None:
        buf.write(text + "\n")

    try:
        conn = get_connection()
    except psycopg2.Error as exc:
        out("Database connection failed.")
        out(str(exc))
        out("Run after: docker compose up -d && load_decisions.py")
        return buf.getvalue()

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (SCHEMA, TABLE),
            )
            columns = [row[0] for row in cur.fetchall()]

            cur.execute(f'SELECT COUNT(*) FROM {SCHEMA}.{TABLE}')
            total_rows = cur.fetchone()[0]

            cur.execute(
                f'SELECT COUNT(*) FROM {SCHEMA}.{TABLE} WHERE "isActive" = TRUE'
            )
            active_rows = cur.fetchone()[0]
    finally:
        conn.close()

    date_columns = [c for c in columns if is_date_field(c)]
    pipeline_columns = [
        c for c in columns
        if c in {"pdfProcessedAt", "removedDetectedAt", "loadedAt", "lastCheckedAt"}
    ]

    out("Date-like columns in raw.decisions (PostgreSQL)")
    out(f"Table: {SCHEMA}.{TABLE}")
    out(f"Total rows: {total_rows:,d}  |  Active rows: {active_rows:,d}")
    out("")
    out("Row grain: one row per decision PDF attachment (case + decision + attachment flattened).")
    out("Column prefix shows origin: case_, caseAtt_, dec_, att_.")
    out("")
    out("A column 'has value' when NOT NULL and btrim(column) <> ''.")

    if total_rows == 0:
        out("")
        out("No rows in table. Run load_decisions.py first.")
        return buf.getvalue()

    counts: dict[str, int] = {}
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                for col in date_columns:
                    quoted = f'"{col}"'
                    cur.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {SCHEMA}.{TABLE}
                        WHERE {quoted} IS NOT NULL
                          AND btrim({quoted}) <> ''
                        """
                    )
                    counts[col] = cur.fetchone()[0]
        finally:
            conn.close()
    except psycopg2.Error as exc:
        out(f"Query failed: {exc}")
        return buf.getvalue()

    by_level: dict[str, list[str]] = defaultdict(list)
    for col in date_columns:
        by_level[db_level_from_column(col)].append(col)

    level_order = [
        ("case", "CASE columns (case_*)"),
        ("case_attachment", "CASE ATTACHMENT columns (caseAtt_*)"),
        ("decision", "DECISION columns (dec_*)"),
        ("decision_attachment", "DECISION ATTACHMENT columns (att_*)"),
        ("pipeline_tracking", "PIPELINE tracking (not from JSON)"),
        ("other", "OTHER"),
    ]

    for level_key, level_title in level_order:
        cols = sorted(by_level.get(level_key, []))
        if not cols:
            continue
        out("")
        out(SEP)
        out(level_title)
        out(f"Rows in table: {total_rows:,d}")
        col_width = max(len(c) for c in cols) + 2
        out("")
        out(f"  {'Column':<{col_width}} {'With value':>12} {'Empty':>12} {'Fill %':>8}")
        out(f"  {'-' * col_width} {'-' * 12} {'-' * 12} {'-' * 8}")

        always_filled: list[str] = []
        for col in cols:
            with_value = counts.get(col, 0)
            empty = total_rows - with_value
            pct = 100.0 * with_value / total_rows if total_rows else 0.0
            out(
                f"  {col:<{col_width}} {with_value:>12,d} {empty:>12,d} {pct:>7.1f}%"
            )
            if with_value == total_rows:
                always_filled.append(col)

        out("")
        if always_filled:
            out("  Always filled on every attachment row (100%):")
            for col in always_filled:
                out(f"    - {col}")
        else:
            out("  Always filled on every attachment row (100%): none")

    # Active-only subset for business columns
    out("")
    out(SEP)
    out("ACTIVE ROWS ONLY (isActive = TRUE)")
    out(f"Rows: {active_rows:,d}")

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                business_cols = [
                    c for c in date_columns
                    if db_level_from_column(c) in {
                        "case", "case_attachment", "decision", "decision_attachment"
                    }
                ]
                active_counts: dict[str, int] = {}
                for col in business_cols:
                    quoted = f'"{col}"'
                    cur.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM {SCHEMA}.{TABLE}
                        WHERE "isActive" = TRUE
                          AND {quoted} IS NOT NULL
                          AND btrim({quoted}) <> ''
                        """
                    )
                    active_counts[col] = cur.fetchone()[0]
        finally:
            conn.close()
    except psycopg2.Error as exc:
        out(f"Active-row query failed: {exc}")
        return buf.getvalue()

    always_active = [
        col for col in business_cols
        if active_counts.get(col, 0) == active_rows and active_rows > 0
    ]
    if always_active:
        out("")
        out("Business date columns filled on every active attachment row:")
        for col in sorted(always_active):
            out(f"  - {col}")
    else:
        out("")
        out("No business date column is filled on every active attachment row.")

    if pipeline_columns:
        out("")
        out("Pipeline timestamps (pdfProcessedAt, loadedAt, ...) are row-level tracking,")
        out("not EC metadata — see counts in PIPELINE section above.")

    return buf.getvalue()


def main() -> None:
    json_text = analyze_json_main()
    db_text = analyze_db()

    JSON_OUTPUT.write_text(json_text, encoding="utf-8")
    DB_OUTPUT.write_text(db_text, encoding="utf-8")

    print(json_text)
    print("\n" + SEP + "\n")
    print(db_text)
    print(f"\nJSON output saved to: {JSON_OUTPUT}")
    print(f"DB output saved to:   {DB_OUTPUT}")


if __name__ == "__main__":
    main()
