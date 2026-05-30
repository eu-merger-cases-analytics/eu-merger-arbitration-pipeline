"""
Checks attachmentLink + metadataReference composite uniqueness in case-data-M.json.

1. Every att_attachmentLink must have a non-empty att_metadataReference.
2. The pair (att_attachmentLink, att_metadataReference) must be unique
   across all rows (no duplicate composite keys).
3. For every att_attachmentLink, report whether it maps to one or more
   distinct att_metadataReference values.

Output is printed to the console and saved to check_attachment_link_ref_output.txt
(overwrites on each run).

Run:
    python analysis/check_attachment_link_ref.py

    docker compose exec python python analysis/check_attachment_link_ref.py
"""

import json
from collections import defaultdict
from io import StringIO
from pathlib import Path

JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "case-data-M.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "check_attachment_link_ref_output.txt"

SEP = "=" * 60


def first(lst):
    """Returns the first element of a list, or None if empty."""
    return lst[0] if lst else None


def collect_attachment_rows(data: dict) -> list[dict]:
    """Collects one record per decision attachment with link, ref, and context."""
    rows = []
    for case in data.values():
        case_number = first(case.get("metadata", {}).get("caseNumber", []))
        for dec in case.get("decisions", []):
            decision_number = first(dec.get("metadata", {}).get("decisionNumber", []))
            for att in dec.get("decisionAttachments", []):
                meta = att.get("metadata", {})
                link = first(meta.get("attachmentLink", []))
                meta_ref = first(meta.get("metadataReference", []))
                name = first(meta.get("attachmentName", []))
                if not link:
                    continue
                rows.append(
                    {
                        "case_number": case_number,
                        "decision_number": decision_number,
                        "metadata_reference": meta_ref,
                        "attachment_link": link,
                        "attachment_name": name,
                    }
                )
    return rows


def main() -> None:
    if not JSON_PATH.exists():
        print(f"[!] File not found: {JSON_PATH}")
        print("    Run first: python ingestion/download_json.py")
        return

    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    rows = collect_attachment_rows(data)

    links_missing_ref: list[dict] = []
    pair_to_rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
    link_to_refs: dict[str, set[str]] = defaultdict(set)
    link_to_rows: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        link = row["attachment_link"]
        meta_ref = row["metadata_reference"]
        link_to_rows[link].append(row)

        if not meta_ref or not str(meta_ref).strip():
            links_missing_ref.append(row)
            continue

        link_to_refs[link].add(meta_ref)
        pair_to_rows[(link, meta_ref)].append(row)

    duplicate_pairs = {
        pair: pair_rows for pair, pair_rows in pair_to_rows.items() if len(pair_rows) > 1
    }
    links_with_multiple_refs = {
        link: refs for link, refs in link_to_refs.items() if len(refs) > 1
    }

    buf = StringIO()

    def out(text=""):
        print(text)
        buf.write(text + "\n")

    out(f"Source: {JSON_PATH}")
    out(f"Total attachment rows (with attachmentLink): {len(rows)}")
    out(f"Unique attachmentLink values:                {len(link_to_rows)}")
    out(f"Unique (link, metadataReference) pairs:      {len(pair_to_rows)}")

    out(f"\n{SEP}")
    out("Check 1: every attachmentLink has a metadataReference")
    if not links_missing_ref:
        out("PASS - every attachmentLink has a non-empty metadataReference.")
    else:
        out(
            f"FAIL - {len(links_missing_ref)} row(s) have attachmentLink "
            "but missing or empty metadataReference."
        )

    out(f"\n{SEP}")
    out("Check 2: (attachmentLink, metadataReference) is unique across all rows")
    if not duplicate_pairs:
        out("PASS - every (attachmentLink, metadataReference) pair appears on exactly one row.")
    else:
        out(
            f"FAIL - {len(duplicate_pairs)} (link, metadataReference) pair(s) "
            "appear on more than one row."
        )

    out(f"\n{SEP}")
    out("Check 3: one metadataReference per attachmentLink")
    if not links_with_multiple_refs:
        out("PASS - every attachmentLink maps to exactly one metadataReference.")
    else:
        out(
            f"INFO - {len(links_with_multiple_refs)} attachmentLink value(s) "
            "map to more than one metadataReference (shared URL across catalogue entries)."
        )

    out(f"\n{SEP}")
    out("Summary")
    out(f"  Rows with link and metadataReference: {len(rows) - len(links_missing_ref)}")
    out(f"  Rows missing/empty metadataReference: {len(links_missing_ref)}")
    out(f"  Unique (link, ref) pairs:             {len(pair_to_rows)}")
    out(f"  Duplicate (link, ref) pairs:          {len(duplicate_pairs)}")
    duplicate_pair_rows = sum(len(pair_rows) for pair_rows in duplicate_pairs.values())
    out(f"  Rows involved in duplicate pairs:     {duplicate_pair_rows}")
    out(f"  Links with a single metadataReference: {len(link_to_refs) - len(links_with_multiple_refs)}")
    out(f"  Links with multiple metadataReferences: {len(links_with_multiple_refs)}")

    if links_missing_ref:
        out(f"\n{SEP}")
        out("Rows with attachmentLink but missing/empty metadataReference:")
        for i, row in enumerate(links_missing_ref[:50], 1):
            out(
                f"  [{i}] {row['case_number']} | {row['decision_number']} | "
                f"link={row['attachment_link']}"
            )
        if len(links_missing_ref) > 50:
            out(f"  ... and {len(links_missing_ref) - 50} more")

    if duplicate_pairs:
        out(f"\n{SEP}")
        out("Duplicate (attachmentLink, metadataReference) pairs:")
        for i, ((link, meta_ref), pair_rows) in enumerate(
            sorted(duplicate_pairs.items(), key=lambda x: (-len(x[1]), x[0][0], x[0][1])),
            1,
        ):
            out(f"\n  [{i}] pair ({len(pair_rows)} rows):")
            out(f"      link: {link}")
            out(f"      metadataReference: {meta_ref}")
            out("    rows:")
            for row in pair_rows:
                out(
                    f"      {row['case_number']} | {row['decision_number']} | "
                    f"name={row['attachment_name']!r}"
                )

    if links_with_multiple_refs:
        out(f"\n{SEP}")
        out("attachmentLink values with multiple metadataReference values:")
        for i, (link, refs) in enumerate(
            sorted(links_with_multiple_refs.items(), key=lambda x: x[0]), 1
        ):
            out(f"\n  [{i}] attachmentLink:")
            out(f"      {link}")
            out(f"    distinct metadataReference values ({len(refs)}):")
            for ref in sorted(refs):
                out(f"      - {ref}")
            out("    rows:")
            for row in link_to_rows[link]:
                out(
                    f"      {row['case_number']} | {row['decision_number']} | "
                    f"{row['metadata_reference']} | name={row['attachment_name']!r}"
                )

    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
