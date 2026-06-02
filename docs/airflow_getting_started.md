# Airflow — väga väikeste sammudega algus

Eesmärk: **mitte** ümber kirjutada pipeline’i, vaid ajastada olemasolevaid käske (`download_json` → `load_decisions` → `load_decision_hits` → `dbt run`), mida täna käivitad käsitsi [`run_commands.md`](run_commands.md) järgi.

**Põhimõte:** iga samm lisab ühe asja. Kui samm töötab, alles siis järgmine.

---

## Mida Airflow teeb (ja mida mitte)

| Airflow teeb | Airflow ei tee (praegu) |
|--------------|-------------------------|
| Sammude järjekord ja sõltuvused | PDF-i märksõnaotsingu loogikat |
| Ajastus (cron) | dbt mudelite kirjutamist |
| Uuesti käivitamine / logid UI-s | Asenda `python` / `dbt` konteinereid |

Sinu skriptid jäävad `scripts/` ja Dockerisse; Airflow käivitab neid **välja** (esialgu `docker compose exec` kaudu).

---

## Samm 0 — otsus (15 min)

1. **Airflow eraldi** esialgu — ära lisa kohe `compose.yml` juurde (vähem konflikte pg/Supersetiga).
2. **Üks DAG** kogu pipeline’ile: `eu_merger_arbitration_daily` (hiljem võid jagada).
3. **PDF-samm eraldi task** — võib kesta tunde; teised sammud ei tohi seda “ootama” jääda, kui hiljem tahad osalist uuendust.

Kontrolli, et käsitsi pipeline töötab:

```powershell
docker compose ps
docker compose exec db pg_isready -U user -d eu-merger-arbitration
```

---

## Samm 1 — Airflow UI ilma sinu DAG-ita (ainult õppimine)

Kasuta ametlikku **standalone** režiimi (kiireim start; mitte tootmiseks).

1. Loo kaust (väljaspool git’i on OK): nt `C:\airflow-learning`
2. Järgi [Apache Airflow Docker quick start](https://airflow.apache.org/docs/apache-airflow/stable/howto/docker-compose/index.html) — `curl` / lae `docker-compose.yaml`, käivita.
3. Ava UI (tavaliselt `http://localhost:8080`), logi sisse, vaata **DAGs** lehte.

**Valmis, kui:** näed Airflow vaikimisi näidis-DAG-e (või tühja nimekirja). Sa ei pea veel oma projekti puudutama.

---

## Samm 2 — “Hello” DAG (üks task, ilma Dockerita)

Projekti juurde (kui oled valmis commit’ima):

```
airflow/
  dags/
    hello_dag.py
  logs/          # .gitignore
```

`hello_dag.py` (minimal):

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    dag_id="hello_eu_merger",
    start_date=datetime(2026, 1, 1),
    schedule=None,  # ainult käsitsi trigger
    catchup=False,
    tags=["learning"],
) as dag:
    BashOperator(
        task_id="say_hello",
        bash_command='echo "Airflow works"',
    )
```

Mount `airflow/dags` Airflow konteinerisse, taaskäivita scheduler/webserver, lülita DAG **On**, **Trigger DAG**.

**Valmis, kui:** task on roheline ja logis on `Airflow works`.

---

## Samm 3 — üks task, mis kutsub sinu `db` kontrolli

Projekti juurkaustas (kus on `compose.yml`):

```bash
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT 1;"
```

DAG-is `BashOperator`:

```python
bash_command=(
    "cd /path/to/eu-merger-arbitration-pipeline && "
    "docker compose exec -T db "
    "psql -U user -d eu-merger-arbitration -c \"SELECT 1;\""
)
```

**Tähelepanek:** Airflow peab nägema Dockerit (`docker` käsk PATH-is) ja projekti kausta. Windowsil:
- lihtsam on käivitada Airflow **samas masinas** kus Docker Desktop;
- `cd` tee absoluutseks (`C:/Users/.../eu-merger-arbitration-pipeline`).

**Valmis, kui:** task läbib ja logis on `1` rida.

---

## Samm 4 — DAG = sama järjekord mis käsitsi (ainult käsitsi trigger)

Lisa taskid **sõltuvustega** (üks fail, `schedule=None`):

| task_id | vastab |
|---------|--------|
| `download_json` | `docker compose exec python python ingestion/download_json.py` |
| `init_raw_schema` | `psql -f /init/create_raw_schema.sql` |
| `load_decisions` | `load_decisions.py` |
| `init_hits_schema` | `create_raw_decision_hits.sql` |
| `load_decision_hits` | `load_decision_hits.py` (võib võtta tunde) |
| `dbt_run` | `docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --profiles-dir ."` |

Järjekord:

```
download_json >> init_raw_schema >> load_decisions >> init_hits_schema >> load_decision_hits >> dbt_run
```

**Ära lisa veel ajakava.** Käivita DAG käsitsi üks kord täisandmetega ainult siis, kui oled valmis.

**Valmis, kui:** kõik taskid rohelised (või tead, et `load_decision_hits` katkestad testis `TEST_LIMIT` env-iga).

---

## Samm 5 — test režiim PDF-sammule

Enne täispikk PDF-i proovi DAG-is `load_decision_hits` taskile env:

```bash
docker compose exec -e TEST_LIMIT=5 python python ingestion/load_decision_hits.py
```

**Valmis, kui:** lühike test läbib < 5 min.

---

## Samm 6 — ajakava (üks kord päevas)

Kui käsitsi trigger töötab, muuda DAG:

```python
schedule="0 3 * * *"  # iga päev 03:00 (serveri aeg)
```

Alusta **harva** (nt `0 3 * * 0` = pühapäev), kui JSON uueneb iga päev.

**Valmis, kui:** järgmine scheduled run ilmub UI-s ilma käsitsi triggerita.

---

## Samm 7 — integreerimine selle repo `compose.yml`-ga (hiljem)

Väike samm korraga:

1. Lisa `airflow/` kaust repo juurde (`dags/`, `plugins/` tühi).
2. Lisa eraldi `compose.airflow.yml` või laienda `compose.yml` **ainult** pärast samm 4 töötab.
3. `depends_on: db` — Airflow ei pea olema samas võrgus kui `python`, kui kasutad `docker compose exec` hostilt.
4. Airflow metastore: eraldi Postgres või SQLite (õppimiseks SQLite OK; meeskonnale Postgres).

Ära tee seda enne samm 3–4 töötamist eraldi Airflow installis.

---

## Samm 8 — paremad praktikad (järgmised nädalad)

| Teema | Soovitus |
|-------|----------|
| Idempotentsus | `download_json` ja `load_decisions` on juba idempotentsed; dokumenteeri käitumine |
| Pikad taskid | `load_decision_hits` → `execution_timeout`, email/Slack `on_failure_callback` |
| SQL init | `init_*` taskid võivad olla `PostgresOperator` (kui Airflow’l on DB connection), mitte bash |
| dbt | hiljem `BashOperator` asemel `DbtRunOperator` (cosmos / astronomer provider) |
| XCom | vältida suurte andmete liigutamist; ainult meta (nt ridade arv) |
| Secrets | `.env` mitte DAG-faili; Airflow Variables / Connections |

---

## Minimaalne DAG-i näide (samm 4 koost)

Kopeeri alles siis, kui samm 3 töötab. Asenda `PROJECT_DIR`.

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/c/Users/katri/software_development/eu-merger-arbitration-pipeline"

def dc_exec(service: str, cmd: str) -> str:
    return f'cd {PROJECT_DIR} && docker compose exec -T {service} {cmd}'

with DAG(
    dag_id="eu_merger_arbitration_manual",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["eu-merger"],
) as dag:
    download = BashOperator(
        task_id="download_json",
        bash_command=dc_exec("python", "python ingestion/download_json.py"),
    )
    init_raw = BashOperator(
        task_id="init_raw_schema",
        bash_command=dc_exec(
            "db",
            'psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql',
        ),
    )
    load_dec = BashOperator(
        task_id="load_decisions",
        bash_command=dc_exec("python", "python ingestion/load_decisions.py"),
    )
    init_hits = BashOperator(
        task_id="init_hits_schema",
        bash_command=dc_exec(
            "db",
            'psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql',
        ),
    )
    load_hits = BashOperator(
        task_id="load_decision_hits",
        bash_command=dc_exec("python", "python ingestion/load_decision_hits.py"),
    )
    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=dc_exec(
            "dbt",
            'bash -c "cd eu_merger_arbitration && dbt run --profiles-dir ."',
        ),
    )

    download >> init_raw >> load_dec >> init_hits >> load_hits >> dbt_run
```

---

## Kontrollnimekiri

- [ ] Samm 1: Airflow UI töötab
- [ ] Samm 2: `hello_dag` roheline
- [ ] Samm 3: `SELECT 1` läbi Dockeri
- [ ] Samm 5: `TEST_LIMIT=5` PDF test
- [ ] Samm 4: täis DAG käsitsi trigger
- [ ] Samm 6: schedule lisatud
- [ ] Samm 7: repo `airflow/` + compose (valikuline)

---

## Seotud dokumendid

- [`run_commands.md`](run_commands.md) — käsitsi käsud (tõe allikas)
- [`data_pipeline.md`](data_pipeline.md) — sammude tähendus
- [`architecture.md`](architecture.md) — Airflow plaanitud (katkendjoon diagrammil)
