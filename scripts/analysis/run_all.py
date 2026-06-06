"""
Runs all analysis scripts in docs/run_commands.md order (one after another).

Stops on the first script that exits with a non-zero status.

Prerequisites (same as running the scripts individually):
  - JSON: ingestion/download_json.py
  - DB tables: load_decisions.py, load_decision_hits.py
  - dbt mart: dbt run (for export_mart_* and check_decision_grain)

Run:
    docker compose exec python python analysis/run_all.py

Optional env for query_decision_hits_sample.py:
    docker compose exec -e ROW_LIMIT=5 python python analysis/run_all.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ANALYSIS_DIR = Path(__file__).resolve().parent

# Same order as docs/run_commands.md §3
SCRIPTS = [
    "inspect_json.py",
    "query_decisions_sample.py",
    "query_decision_hits_sample.py",
    "summarize_decision_hits.py",
    "export_decision_hits_json.py",
    "export_decision_hits_csv.py",
    "export_mart_arbitration_decisions_csv.py",
    "summarize_date_fields.py",
    "check_decision_grain.py",
    "check_attachment_link_ref_uniqueness.py",
]


def main() -> int:
    total = len(SCRIPTS)
    for index, name in enumerate(SCRIPTS, start=1):
        script = ANALYSIS_DIR / name
        if not script.is_file():
            print(f"Missing script: {script}", file=sys.stderr)
            return 1

        print(f"\n{'=' * 60}")
        print(f"[{index}/{total}] {name}")
        print("=" * 60)

        result = subprocess.run([sys.executable, str(script)], check=False)
        if result.returncode != 0:
            print(f"\nStopped: {name} exited with code {result.returncode}", file=sys.stderr)
            return result.returncode

    print(f"\nAll {total} analysis scripts completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
