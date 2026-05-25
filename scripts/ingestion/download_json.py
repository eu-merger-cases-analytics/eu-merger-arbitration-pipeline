"""
Downloads the European Commission merger decisions JSON file
and saves it to data/raw/case-data-M.json.
 
On every run the file is re-downloaded and replaces the existing one.
A temporary file is used during download — if anything goes wrong
(network error, incomplete file, invalid JSON), the temporary file is
deleted and the existing file is left untouched.
"""
 
import json
import logging
from pathlib import Path
 
import requests
 
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
 
URL = "https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json"
DEST = Path(__file__).resolve().parent.parent.parent / "data" / "raw" / "case-data-M.json"
TMP = DEST.with_suffix(".json.tmp")
 
# Minimum number of cases expected in a valid file
MIN_CASES = 1000
 
 
def is_valid(path: Path) -> bool:
    """
    Checks that the downloaded file is a complete, valid JSON file
    with at least MIN_CASES top-level entries.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if len(data) < MIN_CASES:
            log.error("File appears incomplete: only %d cases (expected >= %d)", len(data), MIN_CASES)
            return False
        log.info("File validated: %d cases found", len(data))
        return True
    except json.JSONDecodeError as e:
        log.error("File is not valid JSON: %s", e)
        return False
 
 
def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
 
    # Download to temporary file
    log.info("Downloading: %s", URL)
    try:
        resp = requests.get(URL, timeout=120)
        resp.raise_for_status()
    except requests.HTTPError as e:
        log.error("HTTP error — will retry later: %s", e)
        raise
    except requests.RequestException as e:
        log.error("Network error — will retry later: %s", e)
        raise
 
    TMP.write_bytes(resp.content)
    log.info("Downloaded: %.1f MB", TMP.stat().st_size / 1e6)
 
    # Validate before replacing the existing file
    if not is_valid(TMP):
        TMP.unlink()
        raise RuntimeError("Downloaded file failed validation — existing file kept, will retry later")
 
    # Replace existing file with new one
    TMP.replace(DEST)
    log.info("Saved: %s (%.1f MB)", DEST, DEST.stat().st_size / 1e6)
 
 
if __name__ == "__main__":
    main()