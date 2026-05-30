"""
Summarizes load_decision_hits.py results from raw.decisions and raw.decision_hits.

Writes JSON to summarize_decision_hits_output.json (overwrites on each run)
and prints a short human-readable summary to the console.

Run:
    python analysis/summarize_decision_hits.py

    docker compose exec python python analysis/summarize_decision_hits.py
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

OUTPUT_PATH = Path(__file__).resolve().parent / "summarize_decision_hits_output.json"

SCHEMA = "raw"
ART6_SUBSTRING = "6(1)(b)"
ART8_SUBSTRING = "8(2)"


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def relevant_types_sql(column: str) -> str:
    """SQL fragment: row belongs to Art. 6(1)(b) or 8(2) decision."""
    art6 = ART6_SUBSTRING.replace("'", "''")
    art8 = ART8_SUBSTRING.replace("'", "''")
    return (
        f'("{column}" LIKE \'%{art6}%\' OR "{column}" LIKE \'%{art8}%\')'
    )


def fetch_summary(conn) -> dict:
    rel = relevant_types_sql("dec_decisionTypes")

    with conn.cursor() as cur:
        # --- raw.decisions: cases and attachments ---
        cur.execute(f"""
            SELECT
                COUNT(DISTINCT "case_caseNumber")                          AS total_cases,
                COUNT(*)                                                   AS total_attachments,
                COUNT(*) FILTER (WHERE "isActive" = TRUE)                  AS active_attachments,
                COUNT(*) FILTER (WHERE "pdfProcessedAt" IS NOT NULL)       AS processed_attachments,
                COUNT(*) FILTER (WHERE "isActive" = TRUE
                                   AND "pdfProcessedAt" IS NULL)           AS pending_attachments,
                COUNT(*) FILTER (WHERE "isActive" = FALSE)                 AS inactive_attachments,
                COUNT(DISTINCT "case_caseNumber") FILTER (WHERE {rel})
                                                                           AS relevant_cases,
                COUNT(DISTINCT ("case_caseNumber", "dec_decisionNumber"))
                    FILTER (WHERE {rel})                                   AS relevant_decisions,
                COUNT(*) FILTER (WHERE {rel})                              AS relevant_attachments,
                COUNT(*) FILTER (WHERE {rel} AND "pdfProcessedAt" IS NOT NULL)
                                                                           AS processed_relevant_attachments,
                COUNT(*) FILTER (WHERE {rel} AND "isActive" = TRUE
                                   AND "pdfProcessedAt" IS NULL)           AS pending_relevant_attachments,
                MIN("pdfProcessedAt")                                      AS first_processed_at,
                MAX("pdfProcessedAt")                                      AS last_processed_at
            FROM {SCHEMA}.decisions
        """)
        dec_row = cur.fetchone()

        # --- raw.decision_hits ---
        cur.execute(f"""
            SELECT
                COUNT(*)                                                   AS total_hits,
                COUNT(DISTINCT "case_caseNumber")                          AS matched_cases,
                COUNT(DISTINCT ("case_caseNumber", "dec_decisionNumber"))  AS matched_decisions,
                COUNT(DISTINCT "decision_id")                              AS matched_attachments,
                COUNT(DISTINCT "case_caseNumber") FILTER (WHERE {rel})     AS matched_relevant_cases,
                COUNT(DISTINCT ("case_caseNumber", "dec_decisionNumber"))
                    FILTER (WHERE {rel})                                   AS matched_relevant_decisions,
                COUNT(*) FILTER (WHERE {rel})                              AS relevant_hits,
                MIN("loadedAt")                                            AS first_hit_at,
                MAX("loadedAt")                                            AS last_hit_at
            FROM {SCHEMA}.decision_hits
        """)
        hit_row = cur.fetchone()

        # --- hits by language ---
        cur.execute(f"""
            SELECT "matchedLanguage", COUNT(*) AS cnt
            FROM {SCHEMA}.decision_hits
            GROUP BY "matchedLanguage"
            ORDER BY cnt DESC, "matchedLanguage"
        """)
        hits_by_language = {lang: cnt for lang, cnt in cur.fetchall()}

        # --- top matched keyword patterns ---
        cur.execute(f"""
            SELECT "matchedKeywords", COUNT(*) AS cnt
            FROM {SCHEMA}.decision_hits
            GROUP BY "matchedKeywords"
            ORDER BY cnt DESC, "matchedKeywords"
            LIMIT 15
        """)
        top_keywords = [
            {"pattern": kw, "count": cnt} for kw, cnt in cur.fetchall()
        ]

    def pct(num: int, denom: int) -> float | None:
        if denom == 0:
            return None
        return round(100.0 * num / denom, 2)

    (
        total_cases,
        total_attachments,
        active_attachments,
        processed_attachments,
        pending_attachments,
        inactive_attachments,
        relevant_cases,
        relevant_decisions,
        relevant_attachments,
        processed_relevant_attachments,
        pending_relevant_attachments,
        first_processed_at,
        last_processed_at,
    ) = dec_row

    (
        total_hits,
        matched_cases,
        matched_decisions,
        matched_attachments,
        matched_relevant_cases,
        matched_relevant_decisions,
        relevant_hits,
        first_hit_at,
        last_hit_at,
    ) = hit_row

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "testLimit": os.environ.get("TEST_LIMIT"),
        "processing": {
            "firstProcessedAt": first_processed_at.isoformat() if first_processed_at else None,
            "lastProcessedAt": last_processed_at.isoformat() if last_processed_at else None,
            "processedAttachments": processed_attachments,
            "pendingAttachments": pending_attachments,
            "processedRelevantAttachments": processed_relevant_attachments,
            "pendingRelevantAttachments": pending_relevant_attachments,
            "processingComplete": pending_attachments == 0,
        },
        "totals": {
            "totalCases": total_cases,
            "totalAttachments": total_attachments,
            "activeAttachments": active_attachments,
            "inactiveAttachments": inactive_attachments,
        },
        "relevant": {
            "definition": f"dec_decisionTypes contains '{ART6_SUBSTRING}' or '{ART8_SUBSTRING}'",
            "totalRelevantCases": relevant_cases,
            "totalRelevantDecisions": relevant_decisions,
            "totalRelevantAttachments": relevant_attachments,
        },
        "matches": {
            "totalHits": total_hits,
            "matchedCases": matched_cases,
            "matchedDecisions": matched_decisions,
            "matchedAttachments": matched_attachments,
            "matchedRelevantCases": matched_relevant_cases,
            "matchedRelevantDecisions": matched_relevant_decisions,
            "relevantHits": relevant_hits,
            "firstHitAt": first_hit_at.isoformat() if first_hit_at else None,
            "lastHitAt": last_hit_at.isoformat() if last_hit_at else None,
            "hitsByLanguage": hits_by_language,
            "topKeywordPatterns": top_keywords,
        },
        "rates": {
            "hitRateAllProcessedAttachmentsPct": pct(total_hits, processed_attachments),
            "hitRateRelevantProcessedAttachmentsPct": pct(
                relevant_hits, processed_relevant_attachments
            ),
            "matchedCasesPctOfAllCases": pct(matched_cases, total_cases),
            "matchedCasesPctOfRelevantCases": pct(matched_relevant_cases, relevant_cases),
            "matchedDecisionsPctOfRelevantDecisions": pct(
                matched_relevant_decisions, relevant_decisions
            ),
        },
    }


def print_summary(summary: dict) -> None:
    rel = summary["relevant"]
    m = summary["matches"]
    p = summary["processing"]
    r = summary["rates"]

    print("load_decision_hits summary")
    print("-" * 40)
    print(f"  Cases (all):              {summary['totals']['totalCases']}")
    print(f"  Relevant cases:           {rel['totalRelevantCases']}")
    print(f"  Relevant decisions:       {rel['totalRelevantDecisions']}")
    print(f"  Attachments processed:    {p['processedAttachments']} "
          f"(pending: {p['pendingAttachments']})")
    print(f"  Keyword hits:             {m['totalHits']}")
    print(f"  Matched cases:            {m['matchedCases']} "
          f"({r['matchedCasesPctOfRelevantCases']}% of relevant cases)")
    print(f"  Matched decisions:        {m['matchedDecisions']} "
          f"({r['matchedDecisionsPctOfRelevantDecisions']}% of relevant decisions)")
    if p["lastProcessedAt"]:
        print(f"  Last PDF processed at:    {p['lastProcessedAt']}")
    if m["lastHitAt"]:
        print(f"  Last hit saved at:        {m['lastHitAt']}")


def main() -> None:
    conn = get_connection()
    try:
        summary = fetch_summary(conn)
    finally:
        conn.close()

    OUTPUT_PATH.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print_summary(summary)
    print(f"\nOutput saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
