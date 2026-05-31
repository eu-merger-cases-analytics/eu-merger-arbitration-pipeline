"""
Compares attachment-level vs decision-level counts for relevant Art. 6(1)(b) / 8(2) rows.

A decision may have multiple PDF attachments (e.g. language variants). For dashboard
metrics that count *decisions*, a decision counts as a hit when ANY attachment has
has_keyword_hit = true (bool_or aggregation).

Checks:
  - attachment vs decision counts (denominator and numerator)
  - decisions with multiple attachments
  - whether decision_number alone is unique, or (case_number, decision_number) is required

Output: check_decision_grain_output.txt (overwrites on each run)

Run:
    docker compose exec python python analysis/check_decision_grain.py
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import psycopg2

OUTPUT_PATH = Path(__file__).resolve().parent / "check_decision_grain_output.txt"
SEP = "=" * 72


def get_connection():
    import os

    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def main() -> None:
    buf = StringIO()

    def out(text: str = "") -> None:
        print(text)
        buf.write(text + "\n")

    try:
        conn = get_connection()
    except psycopg2.Error as exc:
        out(f"Database connection failed: {exc}")
        OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
        return

    try:
        with conn.cursor() as cur:
            cur.execute("""
                WITH attachments AS (
                    SELECT *
                    FROM intermediate.int_decisions_with_hits
                ),
                by_decision AS (
                    SELECT
                        case_number,
                        decision_number,
                        bool_or(has_keyword_hit) AS has_keyword_hit,
                        count(*) AS attachment_count,
                        count(*) FILTER (WHERE has_keyword_hit) AS hit_attachment_count,
                        min(decision_adoption_date) AS decision_adoption_date
                    FROM attachments
                    GROUP BY case_number, decision_number
                )
                SELECT
                    (SELECT count(*) FROM attachments),
                    (SELECT count(*) FROM attachments WHERE has_keyword_hit),
                    (SELECT count(*) FROM by_decision),
                    (SELECT count(*) FROM by_decision WHERE has_keyword_hit),
                    (SELECT count(*) FROM by_decision WHERE attachment_count > 1),
                    (SELECT max(attachment_count) FROM by_decision)
            """)
            (
                att_total,
                att_hits,
                dec_total,
                dec_hits,
                multi_attachment_decisions,
                max_attachments,
            ) = cur.fetchone()

            cur.execute("""
                SELECT attachment_count, count(*) AS decision_count
                FROM (
                    SELECT decision_number, count(*) AS attachment_count
                    FROM intermediate.int_decisions_with_hits
                    GROUP BY case_number, decision_number
                ) d
                GROUP BY attachment_count
                ORDER BY attachment_count
            """)
            attachment_distribution = cur.fetchall()

            cur.execute("""
                SELECT
                    count(DISTINCT decision_number) AS distinct_decision_number,
                    count(DISTINCT (case_number, decision_number)) AS distinct_case_decision
                FROM intermediate.int_decisions_with_hits
            """)
            distinct_dec, distinct_pair = cur.fetchone()

            cur.execute("""
                SELECT decision_number, count(DISTINCT case_number) AS case_count
                FROM intermediate.int_decisions_with_hits
                GROUP BY decision_number
                HAVING count(DISTINCT case_number) > 1
                ORDER BY case_count DESC, decision_number
                LIMIT 10
            """)
            decision_number_collisions = cur.fetchall()

            cur.execute("""
                SELECT
                    case_number,
                    decision_number,
                    attachment_count,
                    hit_attachment_count,
                    has_keyword_hit
                FROM (
                    SELECT
                        case_number,
                        decision_number,
                        count(*) AS attachment_count,
                        count(*) FILTER (WHERE has_keyword_hit) AS hit_attachment_count,
                        bool_or(has_keyword_hit) AS has_keyword_hit
                    FROM intermediate.int_decisions_with_hits
                    GROUP BY case_number, decision_number
                ) d
                WHERE attachment_count > 1 AND has_keyword_hit
                ORDER BY hit_attachment_count DESC, attachment_count DESC
                LIMIT 10
            """)
            multi_hit_examples = cur.fetchall()
    finally:
        conn.close()

    out("Decision grain vs attachment grain (relevant Art. 6(1)(b) / 8(2))")
    out("Source: intermediate.int_decisions_with_hits")
    out("")
    out("Business rule for decision-level hit:")
    out("  A decision has a hit when ANY of its attachments has has_keyword_hit = true.")
    out("")
    out(SEP)
    out("COUNTS")
    out(f"  Relevant attachments (denominator, attachment grain):  {att_total:>6,d}")
    out(f"  Relevant decisions   (denominator, decision grain):    {dec_total:>6,d}")
    out(f"  Hit attachments      (numerator, attachment grain):     {att_hits:>6,d}")
    out(f"  Hit decisions        (numerator, decision grain):       {dec_hits:>6,d}")
    out("")
    if att_total:
        out(f"  Hit rate (attachments): {100.0 * att_hits / att_total:.2f}%")
    if dec_total:
        out(f"  Hit rate (decisions):   {100.0 * dec_hits / dec_total:.2f}%")
    out("")
    out(f"  Decisions with >1 attachment: {multi_attachment_decisions:,d}")
    out(f"  Max attachments on one decision: {max_attachments}")

    out("")
    out(SEP)
    out("DECISION KEY")
    out(f"  Distinct decision_number values:              {distinct_dec:,d}")
    out(f"  Distinct (case_number, decision_number):     {distinct_pair:,d}")
    if distinct_dec == distinct_pair:
        out("  In this relevant subset, decision_number is unique (no cross-case collisions).")
        out("  Still use (case_number, decision_number) as the canonical key — safer globally.")
    else:
        out("  decision_number alone is NOT unique — use (case_number, decision_number).")

    if decision_number_collisions:
        out("")
        out("  decision_number values shared across cases (first 10):")
        for dec_num, case_count in decision_number_collisions:
            out(f"    {dec_num}: {case_count} cases")
    else:
        out("  No decision_number shared across different cases in relevant data.")

    out("")
    out(SEP)
    out("ATTACHMENTS PER DECISION")
    for att_count, decision_count in attachment_distribution:
        out(f"  {att_count} attachment(s): {decision_count:,d} decisions")

    out("")
    out(SEP)
    out("EXAMPLES: multi-attachment decisions WITH a hit (first 10)")
    out("  (shows why attachment grain over-counts decisions)")
    if not multi_hit_examples:
        out("  None")
    else:
        for case_num, dec_num, att_cnt, hit_att_cnt, dec_hit in multi_hit_examples:
            out(
                f"  case={case_num} decision={dec_num} | "
                f"{att_cnt} attachments, {hit_att_cnt} with hit, decision_hit={dec_hit}"
            )

    out("")
    out(SEP)
    out("RECOMMENDATION")
    out("  - Keep int_decisions_with_hits at attachment grain (PDF processing, keyword context).")
    out("  - Add decision-grain model for marts/dashboard, e.g. int_relevant_decisions_agg:")
    out("      GROUP BY case_number, decision_number")
    out("      has_keyword_hit = bool_or(has_keyword_hit)")
    out("      decision_adoption_date = min(decision_adoption_date)  -- same on all rows")
    out("  - Mart metrics (counts, share, period filter) should use decision grain.")

    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
