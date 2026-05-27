"""
Searches European Commission merger decision PDFs for arbitration-related
keywords defined in config/keywords.txt.
 
Steps:
  1. Load keyword rules from config/keywords.txt (language-keyed).
  2. Read the downloaded JSON from data/raw/case-data-M.json.
  3. Filter to relevant cases: those with an Art. 6(1)(b) or Art. 8(2) decision.
  4. For each relevant case, find PDF attachments on qualifying decisions.
  5. Download each PDF and search for keywords matching the attachment language.
  6. Write matched records to data/processed/arbitration_hits.jsonl.
 
Usage:
    python scripts/ingestion/ingest.py
 
Optional environment variables:
    TEST_LIMIT    - process only the first N relevant cases (default: 0 = all)
"""
 
import json
import logging
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
 
import pdfplumber
import requests
 
# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
 
# Paths are resolved relative to the project root.
# In Docker: /config, /data, /logs are mounted directly at root level.
# Locally: paths are resolved two levels up from scripts/ingestion/.
_SCRIPT_DIR = Path(__file__).resolve().parent          # scripts/ingestion/
_SCRIPTS_DIR = _SCRIPT_DIR.parent                      # scripts/
PROJECT_ROOT = _SCRIPTS_DIR.parent                     # project root
 
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
LOGS_DIR = PROJECT_ROOT / "logs"
 
DATA_RAW_DIR.mkdir(parents=True, exist_ok=True)
DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
 
RAW_JSON_PATH = DATA_RAW_DIR / "case-data-M.json"
 
# Production output files
HITS_PATH = DATA_PROCESSED_DIR / "arbitration_hits.jsonl"
HITS_READABLE_PATH = DATA_PROCESSED_DIR / "arbitration_hits_readable.json"
SUMMARY_PATH = LOGS_DIR / "ingest_summary.json"
CHECKPOINT_PATH = LOGS_DIR / "checkpoint.json"
 
# Test output files — written instead of production files when TEST_LIMIT is set
TEST_HITS_PATH = DATA_PROCESSED_DIR / "test_arbitration_hits.jsonl"
TEST_HITS_READABLE_PATH = DATA_PROCESSED_DIR / "test_arbitration_hits_readable.json"
TEST_SUMMARY_PATH = LOGS_DIR / "test_ingest_summary.json"
 
KEYWORDS_PATH = CONFIG_DIR / "keywords.txt"
 
# Limit processing to the first N relevant cases for testing. Set to 0 to process all.
TEST_LIMIT = int(os.getenv("TEST_LIMIT", "0"))
 
# Substrings used to identify relevant decision types.
# Using substrings (not exact match) to capture all variants:
# e.g. "Art. 6(1)(b) with conditions & obligations", "Modification of Art. 8(2)" etc.
RELEVANT_DECISION_SUBSTRINGS = ("6(1)(b)", "8(2)")
 
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
 
 
# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
 
def first(lst: list) -> object:
    """Returns the first element of a list, or None if empty."""
    return lst[0] if lst else None
 
 
def parse_label(raw: str) -> str:
    """Parses a JSON-encoded label string, falls back to raw value."""
    try:
        return json.loads(raw).get("label", raw)
    except (json.JSONDecodeError, AttributeError):
        return raw
 
 
def _safe_json_get(raw: str, key: str) -> str | None:
    """Safely extracts a key from a JSON-encoded string, returns None on failure."""
    try:
        return json.loads(raw).get(key)
    except (json.JSONDecodeError, AttributeError):
        return None
 
 
def load_keywords(path: Path) -> dict[str, list[dict]]:
    """
    Loads and parses search rules from keywords.txt.
 
    Each line has the format:  LANG: term  (e.g. "EN: arbitrat*")
    AND condition:             LANG: term1*:term2*  (both must appear in text)
    OR condition:              put each variant on its own line
 
    Returns a dict keyed by uppercase language code:
        {
            "EN": [{"raw": "arbitrat*", "type": "wildcard", "pattern": re.Pattern}],
            "CZ": [{"raw": "rozhodč*:řízen*", "type": "and", "patterns": [...]}],
        }
    """
    if not path.exists():
        raise FileNotFoundError(f"Keywords file not found: {path}")
 
    def _to_pattern(term: str) -> re.Pattern:
        """Converts a search term (may contain *) into a compiled regex pattern."""
        escaped = re.escape(term.lower().replace("*", "\x00"))
        regex = escaped.replace(re.escape("\x00"), r"\S*")
        return re.compile(regex, re.UNICODE)
 
    rules: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            log.warning("Skipping malformed line in keywords file (missing ':'): %s", line)
            continue
 
        lang, _, term = line.partition(":")
        lang = lang.strip().upper()
        term = term.strip()
 
        if not lang or not term:
            log.warning("Skipping malformed line in keywords file: %s", line)
            continue
 
        # AND condition: term itself contains a colon, e.g. "rozhodč*:řízen*"
        if ":" in term:
            parts = [p.strip() for p in term.split(":") if p.strip()]
            rule = {"raw": term, "type": "and", "patterns": [_to_pattern(p) for p in parts]}
        else:
            rule = {"raw": term, "type": "wildcard", "pattern": _to_pattern(term)}
 
        rules.setdefault(lang, []).append(rule)
 
    total = sum(len(v) for v in rules.values())
    and_count = sum(1 for v in rules.values() for r in v if r["type"] == "and")
    log.info(
        "Loaded %d rules for %d languages (%d AND, %d wildcard) from %s",
        total, len(rules), and_count, total - and_count, path,
    )
    return rules
 
 
def is_relevant_case(case: dict) -> bool:
    """Returns True if the case has at least one decision whose label
    contains '6(1)(b)' or '8(2)' — captures all variants including
    'with conditions & obligations' and 'Modification of'.
    """
    for dec in case.get("decisions", []):
        for raw in dec.get("metadata", {}).get("decisionTypes", []):
            label = parse_label(raw)
            if any(sub in label for sub in RELEVANT_DECISION_SUBSTRINGS):
                return True
    return False
 
 
def extract_context(text: str, pattern: re.Pattern, window: int = 100) -> str:
    """
    Extracts a short snippet of text around the first match of the pattern.
    Returns up to `window` characters before and after the match.
    """
    m = pattern.search(text)
    if not m:
        return ""
    start = max(0, m.start() - window)
    end = min(len(text), m.end() + window)
    snippet = text[start:end].strip().replace("\n", " ")
    # Add ellipsis if snippet is cut
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet
 
 
def search_pdf(pdf_bytes: bytes, lang: str, rules: dict[str, list[dict]]) -> list[dict]:
    """
    Searches a PDF for keyword rules matching the given language code.
 
    Only languages present in keywords.txt are searched. If no rules exist
    for the PDF's language (either not defined or all commented out), the PDF
    is skipped and an empty list is returned — no fallback to another language.
 
    Returns a list of match dicts:
        [{"keyword": "arbitrat*", "language": "EN", "context": "...arbitration mechanism..."}]
    """
    lang_upper = lang.upper()
    lang_rules = rules.get(lang_upper, [])
    if not lang_rules:
        log.debug("No keyword rules for language '%s' — skipping PDF", lang_upper)
        return []
 
    found = []
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name
 
        with pdfplumber.open(tmp_path) as pdf:
            full_text = "\n".join(
                (page.extract_text() or "") for page in pdf.pages
            ).lower()
 
        for rule in lang_rules:
            if rule["type"] == "wildcard":
                m = rule["pattern"].search(full_text)
                if m:
                    found.append({
                        "keyword": rule["raw"],
                        "language": lang.upper(),
                        "context": extract_context(full_text, rule["pattern"]),
                    })
            elif rule["type"] == "and":
                if all(p.search(full_text) for p in rule["patterns"]):
                    # Use the first pattern for context extraction
                    found.append({
                        "keyword": rule["raw"],
                        "language": lang.upper(),
                        "context": extract_context(full_text, rule["patterns"][0]),
                    })
 
    except Exception as exc:
        log.warning("PDF search failed (lang=%s): %s", lang, exc)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
 
    return found
 
 
def extract_case_record(case: dict, case_number: str) -> dict:
    """
    Extracts the relevant fields from a case object for the output record.
    All list values are unwrapped to their first element where appropriate.
    """
    meta = case.get("metadata", {})
 
    record = {
        "caseNumber": first(meta.get("caseNumber", [])),
        "caseTitle": first(meta.get("caseTitle", [])),
        "caseCompanies": meta.get("caseCompanies", []),
        "caseInstrument": first(meta.get("caseInstrument", [])),
        "caseRegulation": first(meta.get("caseRegulation", [])),
        "caseSimplified": first(meta.get("caseSimplified", [])),
        "caseSectors": [parse_label(s) for s in meta.get("caseSectors", [])],
        "caseInitiationDate": first(meta.get("caseInitiationDate", [])),
        "caseNotificationDate": first(meta.get("caseNotificationDate", [])),
        "caseDeadlineDate": first(meta.get("caseDeadlineDate", [])),
        "caseLastDecisionDate": first(meta.get("caseLastDecisionDate", [])),
        "caseAttachments": [
            {"metadataReference": first(ca.get("metadata", {}).get("metadataReference", []))}
            for ca in case.get("caseAttachments", [])
        ],
        "decisions": [],
    }
 
    for dec in case.get("decisions", []):
        dm = dec.get("metadata", {})
        decision_record = {
            "decisionNumber": first(dm.get("decisionNumber", [])),
            "decisionAdoptionDate": first(dm.get("decisionAdoptionDate", [])),
            "decisionOfficialJournalPublicationsPublishedDates": dm.get(
                "decisionOfficialJournalPublicationsPublishedDates", []
            ),
            "decisionTypes": [
                {
                    "code": _safe_json_get(r, "code"),
                    "label": parse_label(r),
                }
                for r in dm.get("decisionTypes", [])
            ],
            "decisionAttachments": [
                {
                    "metadataReference": first(att.get("metadata", {}).get("metadataReference", [])),
                    "attachmentLanguage": first(att.get("metadata", {}).get("attachmentLanguage", [])),
                    "language": first(att.get("metadata", {}).get("language", [])),
                    "attachmentName": first(att.get("metadata", {}).get("attachmentName", [])),
                    "attachmentLink": first(att.get("metadata", {}).get("attachmentLink", [])),
                }
                for att in dec.get("decisionAttachments", [])
            ],
        }
        record["decisions"].append(decision_record)
 
    return record
 
 
def process_case(
    case_number: str,
    case: dict,
    rules: dict[str, list[dict]],
    session: requests.Session,
    processed_links: set[str],
    is_test_run: bool,
) -> dict | None:
    """
    Processes a single case:
      1. Iterates over relevant decisions and their PDF attachments.
      2. Skips PDFs already in processed_links (checkpoint).
      3. Downloads each new PDF and searches for keywords by attachment language.
      4. Updates processed_links and checkpoint after each PDF.
      5. Returns a hit record with only the matched decisions if any keyword is found.
    """
    # all_matches: list of {dec_idx, keywords, pdf_url} — one entry per matching PDF
    all_matches = []
 
    # Early skip: check if any attachment language in this case has keyword rules
    case_langs = {
        (first(att.get("metadata", {}).get("attachmentLanguage", [])) or "").upper()
        for dec in case.get("decisions", [])
        for att in dec.get("decisionAttachments", [])
    }
    if not any(lang in rules for lang in case_langs):
        log.debug("No keyword rules for any attachment language in case %s — skipping", case_number)
        return None
 
    for dec_idx, dec in enumerate(case.get("decisions", [])):
        # Only search PDFs from relevant decision types (Art. 6(1)(b) or Art. 8(2))
        dec_labels = [
            parse_label(raw)
            for raw in dec.get("metadata", {}).get("decisionTypes", [])
        ]
        if not any(
            sub in label
            for label in dec_labels
            for sub in RELEVANT_DECISION_SUBSTRINGS
        ):
            continue
 
        for att in dec.get("decisionAttachments", []):
            att_meta = att.get("metadata", {})
            link = first(att_meta.get("attachmentLink", []))
            lang = first(att_meta.get("attachmentLanguage", [])) or ""
 
            if not link or not link.lower().endswith(".pdf"):
                continue
 
            # Skip already-processed PDFs
            if link in processed_links:
                log.debug("Skipping already-processed PDF [%s]: %s", case_number, link)
                continue
 
            try:
                resp = session.get(link, timeout=60)
                resp.raise_for_status()
            except Exception as exc:
                log.debug("PDF download failed [%s] %s: %s", case_number, link, exc)
                continue
 
            found = search_pdf(resp.content, lang, rules)
 
            # Mark PDF as processed and save checkpoint after every PDF
            processed_links.add(link)
            if not is_test_run:
                save_checkpoint(processed_links)
 
            if found:
                all_matches.append({
                    "dec_idx": dec_idx,
                    "keywords": found,
                    "pdfUrl": link,
                })
 
    if not all_matches:
        return None
 
    record = extract_case_record(case, case_number)
 
    # Keep only the decisions where a keyword match was found
    # Build a mapping from original index to output index before filtering
    matched_dec_indices = {m["dec_idx"] for m in all_matches}
    orig_to_output = {
        orig_idx: out_idx
        for out_idx, orig_idx in enumerate(sorted(matched_dec_indices))
    }
    record["decisions"] = [
        dec for i, dec in enumerate(record["decisions"])
        if i in matched_dec_indices
    ]
 
    # Remap dec_idx to index in the output decisions list
    for match in all_matches:
        match["dec_idx"] = orig_to_output.get(match["dec_idx"], match["dec_idx"])
 
    record["_matches"] = all_matches
    record["_processedAt"] = datetime.now(timezone.utc).isoformat()
    return record
 
 
def load_checkpoint() -> set[str]:
    """
    Loads the set of already-processed PDF attachment links from the checkpoint file.
    Returns an empty set if the checkpoint file does not exist.
    Keyed by attachmentLink URL — unique per PDF file.
    """
    if not CHECKPOINT_PATH.exists():
        return set()
    data = json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    processed = set(data.get("processedLinks", []))
    log.info("Checkpoint loaded: %d PDF links already processed", len(processed))
    return processed
 
 
def save_checkpoint(processed_links: set[str]) -> None:
    """Saves the set of processed PDF attachment links to the checkpoint file."""
    CHECKPOINT_PATH.write_text(
        json.dumps({"processedLinks": sorted(processed_links)}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
 
 
# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
 
 
def main() -> None:
    log.info("=== Ingestion started ===")
    start = time.time()
 
    # 1. Load keyword rules
    rules = load_keywords(KEYWORDS_PATH)
 
    # 2. Load JSON
    if not RAW_JSON_PATH.exists():
        raise FileNotFoundError(
            f"JSON file not found: {RAW_JSON_PATH}\n"
            "Run first: python scripts/ingestion/download_json.py"
        )
    log.info("Loading JSON from %s", RAW_JSON_PATH)
    with open(RAW_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
 
    # 3. Filter to relevant cases
    all_cases = list(data.items())  # list of (case_number, case_dict)
    relevant = [(cn, c) for cn, c in all_cases if is_relevant_case(c)]
 
    if TEST_LIMIT > 0:
        relevant = relevant[:TEST_LIMIT]
        log.info("TEST_LIMIT active: processing only the first %d relevant cases", TEST_LIMIT)
 
    # Count total relevant decisions after applying TEST_LIMIT so summary is consistent
    total_relevant_decisions = sum(
        1
        for _, c in relevant
        for dec in c.get("decisions", [])
        for raw in dec.get("metadata", {}).get("decisionTypes", [])
        if any(sub in parse_label(raw) for sub in RELEVANT_DECISION_SUBSTRINGS)
    )
    log.info(
        "Total cases: %d  |  Relevant (Art. 6(1)(b) or Art. 8(2)): %d  |  Relevant decisions: %d",
        len(all_cases), len(relevant), total_relevant_decisions,
    )
 
    # 4. Process PDFs
    # TEST_LIMIT runs are fully isolated — checkpoint is never read or written
    is_test_run = TEST_LIMIT > 0
 
    if is_test_run:
        log.info("TEST_LIMIT active — checkpoint disabled for this run")
        checkpoint = set()
    else:
        checkpoint = load_checkpoint()
        if checkpoint:
            log.info("Resuming from checkpoint: %d PDF links already processed", len(checkpoint))
 
    # On resume, load hits written by the last completed run segment.
    # Note: hits from a crashed run that had not yet written output files are not recoverable —
    # those cases are skipped by checkpoint but their in-progress matches are lost.
    hits = []
    if checkpoint and HITS_PATH.exists():
        with open(HITS_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    hits.append(json.loads(line))
        log.info("Loaded %d existing hits from last written output", len(hits))
 
    processed_links = set(checkpoint)
    session = requests.Session()
    session.headers.update({"User-Agent": "EC-Merger-Research/1.0"})
 
    for i, (cn, case) in enumerate(relevant, 1):
        log.info("Processing case %d / %d: %s", i, len(relevant), cn)
        result = process_case(cn, case, rules, session, processed_links, is_test_run)
        if result is not None:
            hits.append(result)
 
    # 5. Write hits
    log.info("Matches found: %d / %d relevant cases", len(hits), len(relevant))
    hits_path = TEST_HITS_PATH if is_test_run else HITS_PATH
    readable_path = TEST_HITS_READABLE_PATH if is_test_run else HITS_READABLE_PATH
    summary_path = TEST_SUMMARY_PATH if is_test_run else SUMMARY_PATH
    # Machine-readable: one JSON object per line (for dbt)
    with open(hits_path, "w", encoding="utf-8") as f:
        for hit in hits:
            f.write(json.dumps(hit, ensure_ascii=False) + "\n")
    log.info("Results saved to: %s", hits_path)
    # Human-readable: indented JSON array (for reviewing on GitHub)
    with open(readable_path, "w", encoding="utf-8") as f:
        json.dump(hits, f, ensure_ascii=False, indent=2)
    log.info("Readable results saved to: %s", readable_path)
 
    # 6. Write summary
    summary = {
        "totalCases": len(all_cases),
        "totalRelevantCases": len(relevant),
        "totalRelevantDecisions": total_relevant_decisions,
        "matchedCases": len(hits),
        "matchedDecisions": sum(len(h.get("_matches", [])) for h in hits),
        "testLimit": TEST_LIMIT if TEST_LIMIT > 0 else None,
        "processedAt": datetime.now(timezone.utc).isoformat(),
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info("Summary saved to: %s", summary_path)
    # Clear checkpoint on successful completion (only for real runs)
    if not is_test_run and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        log.info("Checkpoint cleared after successful completion")
    log.info("=== Ingestion completed in %.1f s ===", time.time() - start)
 
 
if __name__ == "__main__":
    main()