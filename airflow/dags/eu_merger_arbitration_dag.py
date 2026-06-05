"""
Main pipeline DAG (non-test).

- First run: creates raw.decisions / raw.decision_hits if missing, then loads data and PDFs.
- Later runs: skips init, updates JSON, processes only unprocessed PDFs, dbt, CSV export.

Test DAG with TEST_LIMIT=100: eu_merger_arbitration_test.
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

COMPOSE_EXEC = "python /opt/project/scripts/airflow/compose_exec.py"
# Runs on Airflow container (has docker.sock + /opt/project mount), not via python service
ENSURE_RAW = "/opt/project/scripts/airflow/ensure_raw_table.py"

SCHEDULE = "0 12 * * 0"  # Sundays 12:00 (scheduler timezone)

with DAG(
    dag_id="eu_merger_arbitration",
    start_date=datetime(2026, 1, 1),
    schedule=SCHEDULE,
    catchup=False,
    max_active_runs=1,
    tags=["eu-merger", "pipeline"],
    default_args={"retries": 0},
    doc_md="""
    **Main pipeline** — one DAG for first run and updates.

    | Step | First run | Later runs |
    |------|-----------|------------|
    | ensure raw.decisions | runs `create_raw_schema.sql` | skipped |
    | load_decisions | loads JSON | upserts JSON |
    | ensure raw.decision_hits | runs `create_raw_decision_hits.sql` | skipped |
    | load_decision_hits | processes PDFs (`pdfProcessedAt` null) | only new PDFs |

    Schedule: Sundays 12:00 (`0 12 * * 0`). Keep DAG **unpaused**.

    To wipe raw and rebuild from scratch you must drop dbt views / raw tables first
    (see docs/run_commands.md) — this DAG does not force-drop existing tables.
    """,
) as dag:
    download_json = BashOperator(
        task_id="download_json",
        bash_command=f"{COMPOSE_EXEC} python python ingestion/download_json.py",
    )

    ensure_raw_decisions = BashOperator(
        task_id="ensure_raw_decisions",
        bash_command=f"python {ENSURE_RAW} decisions",
    )

    load_decisions = BashOperator(
        task_id="load_decisions",
        bash_command=f"{COMPOSE_EXEC} python python ingestion/load_decisions.py",
    )

    ensure_raw_hits = BashOperator(
        task_id="ensure_raw_hits",
        bash_command=f"python {ENSURE_RAW} hits",
    )

    load_decision_hits = BashOperator(
        task_id="load_decision_hits",
        bash_command=f"{COMPOSE_EXEC} python python ingestion/load_decision_hits.py",
        execution_timeout=timedelta(hours=12),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=(
            f'{COMPOSE_EXEC} dbt bash -c "cd eu_merger_arbitration && dbt run --profiles-dir ."'
        ),
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=(
            f'{COMPOSE_EXEC} dbt bash -c "cd eu_merger_arbitration && dbt test --profiles-dir ."'
        ),
    )

    export_mart_csv = BashOperator(
        task_id="export_mart_csv",
        bash_command=(
            f"{COMPOSE_EXEC} python python analysis/export_mart_arbitration_decisions_csv.py"
        ),
    )

    (
        download_json
        >> ensure_raw_decisions
        >> load_decisions
        >> ensure_raw_hits
        >> load_decision_hits
        >> dbt_run
        >> dbt_test
        >> export_mart_csv
    )
