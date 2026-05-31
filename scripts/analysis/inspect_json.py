"""
Explores the structure of the downloaded JSON file before any processing.
All statistics are for Art. 6(1)(b) and Art. 8(2) cases only unless stated otherwise.
Output is printed to the console and saved to inspect_json_output.txt
in the same folder. Re-running overwrites the file.
 
Run after download_json.py:
    python analysis/inspect_json.py
"""
 
import json
import re
from collections import Counter
from io import StringIO
from pathlib import Path
 
JSON_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "case-data-M.json"
OUTPUT_PATH = Path(__file__).resolve().parent / "inspect_json_output.txt"
 
SEP = "=" * 60
 
# Substrings used to detect all variants of the articles of interest
ART6_SUBSTRING = "6(1)(b)"
ART8_SUBSTRING = "8(2)"
 
 
def first(lst):
    """Returns the first element of a list, or None if empty."""
    return lst[0] if lst else None
 
 
def parse_label(raw):
    """Parses a JSON-encoded label string, falls back to raw value."""
    try:
        return json.loads(raw).get("label", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw
 
 
def case_has_relevant_decision(case):
    """Returns True if the case has at least one decision label containing
    '6(1)(b)' or '8(2)'."""
    for dec in case.get("decisions", []):
        for raw in dec.get("metadata", {}).get("decisionTypes", []):
            label = parse_label(raw)
            if ART6_SUBSTRING in label or ART8_SUBSTRING in label:
                return True
    return False
 
 
def main() -> None:
    if not JSON_PATH.exists():
        print(f"[!] File not found: {JSON_PATH}")
        print("    Run first: python ingestion/download_json.py")
        return
 
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
 
    buf = StringIO()
 
    def out(text=""):
        print(text)
        buf.write(text + "\n")
 
    all_cases = list(data.values())
    relevant_cases = [c for c in all_cases if case_has_relevant_decision(c)]
 
    out(f"Note: all statistics below are for cases containing '6(1)(b)' or '8(2)' in JSON raw file")
    out(f"decisionTypes labels, unless stated otherwise.")
 
    # --- Totals ---
    out(f"\n{SEP}")
    out(f"Total cases in file:                        {len(all_cases)}")
    out(f"Cases with 6(1)(b) or 8(2) decision:        {len(relevant_cases)}")
 
    # --- Attachments count ---
    out(f"\n{SEP}")
    cases_with_att = sum(
        1 for case in relevant_cases
        if any(dec.get("decisionAttachments") for dec in case.get("decisions", []))
    )
    total_att = sum(
        len(dec.get("decisionAttachments", []))
        for case in relevant_cases
        for dec in case.get("decisions", [])
    )
    out(f"Cases with at least one attachment:          {cases_with_att}")
    out(f"Total decision attachments:                  {total_att}")
 
    # --- Decisions per relevant case ---
    out(f"\n{SEP}")
    out("Decisions per case:")
    dec_counts = Counter(len(c.get("decisions", [])) for c in relevant_cases)
    for count, freq in sorted(dec_counts.items()):
        out(f"  {count} decision(s): {freq} cases")
 
    # --- All label variants ---
    out(f"\n{SEP}")
    out("All label variants containing '6(1)(b)':")
    art6_variants = Counter()
    art8_variants = Counter()
    for case in relevant_cases:
        for dec in case.get("decisions", []):
            for raw in dec.get("metadata", {}).get("decisionTypes", []):
                label = parse_label(raw)
                if ART6_SUBSTRING in label:
                    art6_variants[label] += 1
                elif ART8_SUBSTRING in label:
                    art8_variants[label] += 1
    for label, cnt in art6_variants.most_common():
        out(f"  {cnt:6d}  {label}")
 
    out(f"\nAll label variants containing '8(2)':")
    for label, cnt in art8_variants.most_common():
        out(f"  {cnt:6d}  {label}")
 
    # --- caseRegulation breakdown ---
    out(f"\n{SEP}")
    out("caseRegulation breakdown:")
    regulations = Counter(
        first(c.get("metadata", {}).get("caseRegulation", [])) or "unknown"
        for c in relevant_cases
    )
    for reg, cnt in regulations.most_common():
        out(f"  {reg:50s} {cnt:6d}")
 
    # --- caseSimplified breakdown ---
    out(f"\n{SEP}")
    out("caseSimplified breakdown:")
    simplified = Counter(
        first(c.get("metadata", {}).get("caseSimplified", [])) or "unknown"
        for c in relevant_cases
    )
    for val, cnt in simplified.most_common():
        out(f"  {val:50s} {cnt:6d}")
 
    # --- Attachment languages ---
    out(f"\n{SEP}")
    out("Attachment languages (all, sorted by count):")
    att_langs = Counter()
    for case in relevant_cases:
        for dec in case.get("decisions", []):
            for att in dec.get("decisionAttachments", []):
                lang = first(att.get("metadata", {}).get("attachmentLanguage", []))
                att_langs[lang or "unknown"] += 1
    for lang, cnt in att_langs.most_common():
        out(f"  {lang:10s} {cnt:6d}")
 
    # --- attachmentLanguage vs language consistency check ---
    out(f"\n{SEP}")
    out("Consistency check: attachmentLanguage vs language field in decisionAttachments:")
    mismatches = []
    for case in relevant_cases:
        case_number = first(case.get("metadata", {}).get("caseNumber", []))
        for dec in case.get("decisions", []):
            for att in dec.get("decisionAttachments", []):
                am = att.get("metadata", {})
                att_lang = (first(am.get("attachmentLanguage", [])) or "").upper()
                lang = (first(am.get("language", [])) or "").upper()
                meta_ref = first(am.get("metadataReference", []))
                if att_lang and lang and att_lang != lang:
                    mismatches.append(
                        f"  {case_number} | {meta_ref} | "
                        f"attachmentLanguage={att_lang} | language={lang}"
                    )
    if mismatches:
        out(f"  {len(mismatches)} mismatches found:")
        for m in mismatches[:20]:
            out(m)
        if len(mismatches) > 20:
            out(f"  ... and {len(mismatches) - 20} more")
    else:
        out("  All checked — attachmentLanguage and language always match.")
 
    # --- Sectors by NACE division ---
    out(f"\n{SEP}")
    out("Sectors by NACE division:")
    division_labels = {}
    division_counts = Counter()
    for case in relevant_cases:
        for raw in case.get("metadata", {}).get("caseSectors", []):
            label = parse_label(raw)
            m = re.match(r'^([A-Z]\.\d+)', label)
            if m:
                division = m.group(1)
                if division not in division_labels:
                    division_labels[division] = label.split(' - ', 1)[1].strip() if ' - ' in label else label
                division_counts[division] += 1
            else:
                division_counts[label] += 1
    col_width = max(
        (len(f"{div}  {division_labels.get(div, '')}") for div in division_counts),
        default=40
    ) + 2
    for division, cnt in sorted(
        division_counts.items(),
        key=lambda x: (x[0][0], int(x[0][1:].split('.')[1])
                       if len(x[0]) > 1 and x[0][1:].lstrip('.').split('.')[0].isdigit() else 0)
    ):
        desc = division_labels.get(division, '')
        line = f"{division}  {desc}"
        out(f"  {line:<{col_width}} {cnt:6d}")
 
    # --- Sample case ---
    out(f"\n{SEP}")
    out("Sample relevant case (first match):")
    sample = relevant_cases[0]
    meta = sample.get("metadata", {})
    out(f"  caseNumber:           {first(meta.get('caseNumber', []))}")
    out(f"  caseTitle:            {first(meta.get('caseTitle', []))}")
    out(f"  caseCompanies:        {meta.get('caseCompanies', [])}")
    out(f"  caseInstrument:       {first(meta.get('caseInstrument', []))}")
    out(f"  caseRegulation:       {first(meta.get('caseRegulation', []))}")
    out(f"  caseSimplified:       {first(meta.get('caseSimplified', []))}")
    out(f"  caseSectors:          {[parse_label(s) for s in meta.get('caseSectors', [])]}")
    out(f"  caseInitiationDate:   {first(meta.get('caseInitiationDate', []))}")
    out(f"  caseNotificationDate: {first(meta.get('caseNotificationDate', []))}")
    out(f"  caseDeadlineDate:     {first(meta.get('caseDeadlineDate', []))}")
    out(f"  caseLastDecisionDate: {first(meta.get('caseLastDecisionDate', []))}")
 
    out(f"\n  caseAttachments ({len(sample.get('caseAttachments', []))}):")
    for ca in sample.get("caseAttachments", []):
        cam = ca.get("metadata", {})
        out(f"    metadataReference: {first(cam.get('metadataReference', []))}")
 
    out(f"\n  decisions ({len(sample.get('decisions', []))}):")
    for i, dec in enumerate(sample.get("decisions", [])):
        dm = dec.get("metadata", {})
        types = [parse_label(r) for r in dm.get("decisionTypes", [])]
        out(f"    decision[{i}]:")
        out(f"      decisionNumber:           {first(dm.get('decisionNumber', []))}")
        out(f"      metadataReference:        {first(dm.get('metadataReference', []))}")
        out(f"      decisionAdoptionDate:     {first(dm.get('decisionAdoptionDate', []))}")
        out(f"      decisionOJPublishedDates: {dm.get('decisionOfficialJournalPublicationsPublishedDates', [])}")
        out(f"      decisionTypes:            {types}")
        out(f"      decisionAttachments ({len(dec.get('decisionAttachments', []))}):")
        for att in dec.get("decisionAttachments", []):
            am = att.get("metadata", {})
            out(f"        metadataReference:  {first(am.get('metadataReference', []))}")
            out(f"        attachmentLanguage: {first(am.get('attachmentLanguage', []))}")
            out(f"        language:           {first(am.get('language', []))}")
            out(f"        attachmentName:     {first(am.get('attachmentName', []))}")
            out(f"        attachmentLink:     {first(am.get('attachmentLink', []))}")
 
    # --- metadataReference uniqueness check ---
    out(f"\n{SEP}")
    out("metadataReference uniqueness check (decisionAttachments across all cases):")
    all_refs = []
    for case in data.values():
        for dec in case.get("decisions", []):
            for att in dec.get("decisionAttachments", []):
                ref = first(att.get("metadata", {}).get("metadataReference", []))
                if ref:
                    all_refs.append(ref)
    total_refs = len(all_refs)
    unique_refs = len(set(all_refs))
    duplicates = total_refs - unique_refs
    out(f"  Total attachment metadataReferences:  {total_refs}")
    out(f"  Unique metadataReferences:            {unique_refs}")
    out(f"  Duplicates:                           {duplicates}")
    if duplicates > 0:
        from collections import Counter as _Counter
        counts = _Counter(all_refs)
        out("  Duplicate values (first 10):")
        for ref, cnt in counts.most_common(10):
            if cnt > 1:
                out(f"    {ref}: {cnt} times")
 
    # --- Multi-value field check ---
    out(f"\n{SEP}")
    out("Fields with more than one value (across all cases and decisions):")
 
    # Case metadata fields
    case_multi = Counter()
    for case in data.values():
        for key, val in case.get("metadata", {}).items():
            if isinstance(val, list) and len(val) > 1:
                case_multi[key] += 1
 
    # Decision metadata fields
    dec_multi = Counter()
    for case in data.values():
        for dec in case.get("decisions", []):
            for key, val in dec.get("metadata", {}).items():
                if isinstance(val, list) and len(val) > 1:
                    dec_multi[key] += 1
 
    # Attachment metadata fields
    att_multi = Counter()
    for case in data.values():
        for dec in case.get("decisions", []):
            for att in dec.get("decisionAttachments", []):
                for key, val in att.get("metadata", {}).items():
                    if isinstance(val, list) and len(val) > 1:
                        att_multi[key] += 1
 
    if case_multi:
        out("  Case metadata:")
        for key, cnt in case_multi.most_common():
            out(f"    {key:60s} {cnt:6d} cases")
    else:
        out("  Case metadata: no multi-value fields found")
 
    if dec_multi:
        out("  Decision metadata:")
        for key, cnt in dec_multi.most_common():
            out(f"    {key:60s} {cnt:6d} decisions")
    else:
        out("  Decision metadata: no multi-value fields found")
 
    if att_multi:
        out("  Attachment metadata:")
        for key, cnt in att_multi.most_common():
            out(f"    {key:60s} {cnt:6d} attachments")
    else:
        out("  Attachment metadata: no multi-value fields found")
 
    # --- attachmentLink uniqueness per decision check ---
    out(f"\n{SEP}")
    out("attachmentLink uniqueness check (per decision):")
    from collections import Counter as _Counter2
    att_link_dec_pairs = []
    for case in data.values():
        for dec in case.get("decisions", []):
            dec_num = first(dec.get("metadata", {}).get("decisionNumber", []))
            for att in dec.get("decisionAttachments", []):
                link = first(att.get("metadata", {}).get("attachmentLink", []))
                if link:
                    att_link_dec_pairs.append((link, dec_num))
    pair_counts = _Counter2(att_link_dec_pairs)
    duplicates = {k: v for k, v in pair_counts.items() if v > 1}
    out(f"  Total (attachmentLink, decisionNumber) pairs: {len(att_link_dec_pairs)}")
    out(f"  Duplicate pairs: {len(duplicates)}")
    if duplicates:
        out("  Examples (first 10):")
        for (link, dec), count in list(duplicates.items())[:10]:
            out(f"    {link} | decision {dec}: {count} times")
    else:
        out("  All checked — attachmentLink is unique per decision.")
 
    # --- Save to file ---
    OUTPUT_PATH.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nOutput saved to: {OUTPUT_PATH}")
 
 
if __name__ == "__main__":
    main()