# Edenemisraport

## Mis on valmis

- **Dokumentatsioon** — README, arhitektuur, andmevoog, käskude juhend (`run_commands.md`).
- **Docker** — `compose.yml`, Python / dbt / Airflow / Superset konteinerid.
- **Konfiguratsioon** — märksõnad (`keywords.txt`), Airflow ajakava (`airflow_schedule.txt`).
- **Sissevõtt** — JSON allalaadimine, `raw.decisions` ja `raw.decision_hits` laadimine, PDF märksõnaotsing.
- **dbt** — staging → intermediate → marts, andmekvaliteedi testid.
- **Väljund** — Superset dashboard, CSV ekspordid (`decision_hits.csv`, `mart_arbitration_decisions.csv`).
- **Airflow** — põhi-DAG ja test-DAG (JSON → raw → dbt → test → CSV).

Detailid: [`data_pipeline.md`](data_pipeline.md).
