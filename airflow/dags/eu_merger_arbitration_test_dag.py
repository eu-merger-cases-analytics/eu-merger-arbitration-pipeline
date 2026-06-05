"""
Test pipeline DAG: includes init SQL + load_decision_hits with TEST_LIMIT=100.

Use for smoke tests. Production: eu_merger_arbitration (creates tables on first run automatically).
"""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

COMPOSE_EXEC = "python /opt/project/scripts/airflow/compose_exec.py"

with DAG(
    dag_id="eu_merger_arbitration_test",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["eu-merger", "pipeline", "test"],
    default_args={"retries": 0},
    doc_md="""
    **Test pipeline** — `load_decision_hits` stops after 100 unprocessed PDFs.

    Production DAG: `eu_merger_arbitration`.
    """,
) as dag:
    download_json = BashOperator(
        task_id="download_json",
        bash_command=f"{COMPOSE_EXEC} python python ingestion/download_json.py",
    )

    init_raw_schema = BashOperator(
        task_id="init_raw_schema",
        bash_command=(
            f"{COMPOSE_EXEC} db psql -U user -d eu-merger-arbitration "
            "-f /init/create_raw_schema.sql"
        ),
    )

    load_decisions = BashOperator(
        task_id="load_decisions",
        bash_command=f"{COMPOSE_EXEC} python python ingestion/load_decisions.py",
    )

    init_hits_schema = BashOperator(
        task_id="init_hits_schema",
        bash_command=(
            f"{COMPOSE_EXEC} db psql -U user -d eu-merger-arbitration "
            "-f /init/create_raw_decision_hits.sql"
        ),
    )

    load_decision_hits = BashOperator(
        task_id="load_decision_hits",
        bash_command=f"{COMPOSE_EXEC} python python ingestion/load_decision_hits.py",
        env={"TEST_LIMIT": "100"},
        execution_timeout=timedelta(hours=2),
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
        >> init_raw_schema
        >> load_decisions
        >> init_hits_schema
        >> load_decision_hits
        >> dbt_run
        >> dbt_test
        >> export_mart_csv
    )
