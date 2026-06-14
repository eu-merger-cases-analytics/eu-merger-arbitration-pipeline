# Run Commands (EN - ET below from row 389)

Detailed data pipeline description: [`data_pipeline.md`](data_pipeline.md).

All commands assume you are in the root folder of the project and the Docker containers are up. (`docker compose up -d --build`).

## Data pipeline

| Section | Element | What it does |
|------|--------|-----------|
| 1 | Environment | Docker + `.env` |
| 2 | Data ingestion | JSON → `raw.decisions` → PDFs → `raw.decision_hits` |
| 3 | Analysis *(optional)* | Development and Quality Checks|
| 4 | dbt | `raw` → `staging` → `intermediate` → `marts` |
| 5 | Database | psql and sample queries |
| 6 | Superset | Dashboard test `http://localhost:8088` |
| 7 | Airflow | Init + UI `http://localhost:8080`, DAG `eu_merger_arbitration` |

---

## Prerequisites

- Docker Desktop (or Docker Engine + Compose)
- Git
- Stable connection to the internet (esp for PDFs download step)
- `.env` file (`cp .env.example .env`)

---

## 1. Environment and containers

```bash
cp .env.example .env

# All services (including Airflow): docker compose up -d --build

Without Airflow: docker compose up -d --build db python dbt superset

docker compose ps
```

At the first startup of Airflow (which may take a few minutes):

```bash
docker compose up airflow-init
docker compose up -d airflow-api-server airflow-scheduler airflow-dag-processor
```

If you are using `docker compose up -d --build` above, `airflow-init` will start automatically.

---

## 2. Data ingestion (Python)

### Mandatory order

```bash
# Download the JSON → data/raw/case-data-M.json
docker compose exec python python ingestion/download_json.py

# Raw schema + raw.decisions table
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql

# Check: raw.decisions
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name;"

# JSON → raw.decisions
docker compose exec python python ingestion/load_decisions.py

# raw.decision_hits table
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql

# Check: raw.decisions + raw.decision_hits
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name;"

# PDFs → keyword search → raw.decision_hits (takes hours at first run; if aborted, resumes upon restart by pdfProcessedAt)
docker compose exec python python ingestion/load_decision_hits.py
```

### PDF processing options

Default: `REQUEST_DELAY_SECONDS=0` (pdfs ingested sequentially without a delay period). If you come across a lot of `download` errors, try adding a delay or processing only the rows with errors:

```bash
# Delay between PDFs (eg, 1 s)
docker compose exec -e REQUEST_DELAY_SECONDS=1 python python ingestion/load_decision_hits.py

# Only the next N unprocessed PDFs (replace 5 with your preferred number)
docker compose exec -e TEST_LIMIT=5 python python ingestion/load_decision_hits.py

# Reload only rows with download errors 
docker compose exec -e RETRY_DOWNLOAD_ERRORS=1 -e REQUEST_DELAY_SECONDS=2 python python ingestion/load_decision_hits.py
```

---

## 3. Analysis and checks (optional)

These scripts **do not form part of the** automatic pipeline; they are useful for development and quality control.

**All in a row** (same order as above; stops at the first error):

```bash
docker compose exec python python analysis/run_all.py
```

Assumes: `download_json` → `load_decisions` → `load_decision_hits` → `dbt run` has been run (for mart ja grain scripts).

Optional `ROW_LIMIT` for `query_decision_hits_sample.py`:

```bash
docker compose exec -e ROW_LIMIT=5 python python analysis/run_all.py
```

**Individual scripts:**

```bash
# JSON structure
docker compose exec python python analysis/inspect_json.py

# One sample row from raw.decisions (by the first decision_id)
docker compose exec python python analysis/query_decisions_sample.py

# Querying the required number of rows from the decision_hits table
docker compose exec -e ROW_LIMIT=5 python python analysis/query_decision_hits_sample.py

# Summary of the PDF processing and hits → summarize_decision_hits_output.json
docker compose exec python python analysis/summarize_decision_hits.py

# JSON-file with the rows with hits → data\processed\decision_hits.json
docker compose exec python python analysis/export_decision_hits_json.py

# raw.decision_hits in CSV format → data\processed\decision_hits.csv (assumes load_decision_hits)
docker compose exec python python analysis/export_decision_hits_csv.py

# Mart table in CSV format → data\processed\mart_arbitration_decisions.csv (assumes dbt run)
docker compose exec python python analysis/export_mart_arbitration_decisions_csv.py

# Check the existence of date values in the JSON ja raw.decisions table
docker compose exec python python analysis/summarize_date_fields.py

# Attachment vs decision level (check the calculation of hits after running dbt) 
docker compose exec python python analysis/check_decision_grain.py

# Uniqueness check (link + metadataReference)
docker compose exec python python analysis/check_attachment_link_ref_uniqueness.py
```

---

## 4. dbt

Run after section 2. Models will appear in the Postgres schemas **`staging`**, **`intermediate`**, **`marts`**.

**Models:** `stg_decisions`, `stg_decision_hits` → `int_relevant_decisions`, `int_decisions_with_hits` → `mart_arbitration_decisions`

### Mandatory order

```bash
# 1. All models (staging + intermediate + marts)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --profiles-dir ."

# 2. Checks
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt test --profiles-dir ."
```

### Layer by layer (for development)

```bash
# Staging only
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select staging --profiles-dir ."

# Intermediate only (assumes staging has run)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select intermediate --profiles-dir ."

# Marts only (assumes intermediate has run)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select marts --profiles-dir ."

# Single model
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select mart_arbitration_decisions --profiles-dir ."

# Syntax check (checks without running whether the dbt project files ja structure are OK)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt parse --profiles-dir ."
```

### Check after dbt run

```bash
# Schemas, views and tables
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('staging', 'intermediate', 'marts')
ORDER BY table_schema, table_name;"

# Relevant PDFs and hits (attachment level granularity)
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) AS relevant_attachments,
  COUNT(*) FILTER (WHERE has_keyword_hit) AS with_keyword_hit
FROM intermediate.int_decisions_with_hits;"

# Relevant decisions, hits and proportion (decision level granularity)
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) AS relevant_decisions,
  COUNT(*) FILTER (WHERE has_keyword_hit) AS decisions_with_hit,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE has_keyword_hit) / NULLIF(COUNT(*), 0),
    2
  ) AS hit_share_pct
FROM marts.mart_arbitration_decisions;"
```

---

## 5. Database

```bash
# PostgreSQL interactive command line client (psql) in the db container.
# Opens a session with the eu-merger-arbitration database; can run SQL queries
# directly in the terminal (eg, SELECT * FROM marts.mart_arbitration_decisions LIMIT 5;).
# Schemas: raw, staging, intermediate, marts. Exit: \q
docker compose exec db psql -U user -d eu-merger-arbitration

# Example: number of hits
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT COUNT(*) FROM raw.decision_hits;"

# Example: PDF processing status
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) FILTER (WHERE \"pdfProcessedAt\" IS NULL) AS pending,
  COUNT(*) FILTER (WHERE \"pdfProcessingError\" IS NULL AND \"pdfProcessedAt\" IS NOT NULL) AS ok,
  COUNT(*) FILTER (WHERE \"pdfProcessingError\" LIKE 'download:%') AS download_errors
FROM raw.decisions WHERE \"isActive\" = TRUE;"
```

---

## 6. Superset

Apache Superset **6.0.0** (`Dockerfile.superset` — lean image + `psycopg2-binary`). Superset's own metadata is in SQLite; the data comes from the existing Postgres (`marts`).

**Assumes:** Section 4 is completed (`mart_arbitration_decisions` exists).

```bash
# Start Superset (first time can take time — image download + init)
docker compose up -d superset

# Logs (wait until "Starting Superset on http://localhost:8088")
docker compose logs -f superset
```

Open in browser: **http://localhost:8088**  
Default login (CHANGE THIS): `admin` / `admin` (change in the `.env` file `SUPERSET_ADMIN_*`).

### Database connection in Superset

1. ** '+' dropdown → Data → Connect database →**
2. Select **PostgreSQL**
3. Select **Connect this database with a SQLAlchemy URI string instead** (Docker network, mitte localhost):

   ```
   postgresql+psycopg2://user:user@db:5432/eu-merger-arbitration
   ```

4. **Test connection** → **Connect**

### Dashboard ZIP import

The script imports **the newest** `.zip` file from the `docs/dashboard/` folder via Superset REST API (same content as UI import).

**Assumes:** Superset is running and `mart_arbitration_decisions` exists.

```bash
docker compose exec python python superset/import_dashboard.py
```

The script reads `SUPERSET_ADMIN_*` and `POSTGRES_PASSWORD` from `.env`. Then open **http://localhost:8088** → **Dashboards**.

Manually (without script): **Settings → Import dashboards** → `docs/dashboard/dashboard_export_20260605.zip` → password `POSTGRES_PASSWORD` (default `user`).

### Dataset and chart

1. ** '+' dropdown → Data → Create Dataset** → choose connection → **`marts`** schema → table **`mart_arbitration_decisions`**
2. **Charts → + Chart** → choose dataset
3. Add filter **`decision_adoption_date`** (Time range)
4. Eg, **Big Number**: metric `COUNT(*)`, period filter 
5. Second chart: `COUNT(*)` where `has_keyword_hit = true`, or **Table** / **Pie** by sector label or sector code

---

## 7. Airflow

Airflow is in `compose.yml` (`airflow-postgres`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`). DAGs are in the `airflow/dags/` repo. Airflow's **metadata** is in a separate Postgres (`airflow-postgres`); pipeline data is still in `db` (port **5434**).

**Assumes:** `.env` contains `AIRFLOW_*` values ​​(see `.env.example`).

### Install and init (first run)

```bash
# After updating the Airflow image, rebuild all Airflow services
docker compose build airflow-init airflow-api-server airflow-scheduler airflow-dag-processor

# 1. Metastore + admin user (one-time step; wait until container finishes)
docker compose up airflow-init

# 2. UI and scheduler
docker compose up -d airflow-api-server airflow-scheduler airflow-dag-processor

# Logs (wait until api-server is healthy)
docker compose logs -f airflow-api-server
```

Or run with one command along with the rest of the stack:

```bash
docker compose up -d --build
```

### UI and login

- Address: **http://localhost:8080**
- Login: `.env` → `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (default `admin` / `admin`)

### Pipeline DAGs

| DAG | Usage |
|-----|--------|
| **`eu_merger_arbitration`** | **Main DAG** — on first run, creates `raw` tables if none exist; later updates data and processes new PDFs. Runtime specified in `config\airflow_schedule.txt` |
| **`eu_merger_arbitration_test`** | Test — `TEST_LIMIT=100` PDFs + init (optional before main DAG) |

### Stopping Airflow (rest of stack will remain running)

```bash
docker compose stop airflow-api-server airflow-scheduler airflow-dag-processor
```

### Airflow metastore from scratch (deletes Airflow DB and logs)

```bash
docker compose down
docker volume rm eu-merger-arbitration-airflow-pg
docker compose up airflow-init
docker compose up -d airflow-api-server airflow-scheduler airflow-dag-processor
```

---

## 8. Stopping containers

```bash
docker compose down
```

---

## 9. Starting from scratch

### Full reset (Postgres volume will be deleted)

```bash
docker compose down -v

# Optional: Delete local JSON and analysis outputs (Windows PowerShell)
# Remove-Item -Force data/raw/case-data-M.json -ErrorAction SilentlyContinue
# Remove-Item -Force scripts/analysis/*_output.txt, scripts/analysis/summarize_decision_hits_output.json -ErrorAction SilentlyContinue

docker compose up -d --build
docker compose ps
```

Then repeat **Section 2** step by step, then **Section 4** (dbt).

### Clearing raw tables only (containers remain running)

```bash
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql
docker compose exec python python ingestion/load_decisions.py
docker compose exec python python ingestion/load_decision_hits.py
```

`create_raw_schema.sql` first deletes `raw.decision_hits`, then `raw.decisions`.

---


# Käivitamise käsud

Täpsem andmevoo kirjeldus: [`data_pipeline.md`](data_pipeline.md).

Kõik käsud eeldavad, et oled projekti juurkaustas ja Docker Compose konteinerid on üleval (`docker compose up -d --build`).

## Andmevoog

| Samm | Jaotis | Mida teeb |
|------|--------|-----------|
| 1 | Keskkond | Docker + `.env` |
| 2 | Andmete laadimine | JSON → `raw.decisions` → PDF-id → `raw.decision_hits` |
| 3 | Analüüs *(valikuline)* | Arenduse ja kvaliteedi kontroll |
| 4 | dbt | `raw` → `staging` → `intermediate` → `marts` |
| 5 | Andmebaas | psql ja näidispäringud |
| 6 | Superset | Dashboard test `http://localhost:8088` |
| 7 | Airflow | Init + UI `http://localhost:8080`, DAG `eu_merger_arbitration` |

---

## Eeltingimused

- Docker Desktop (või Docker Engine + Compose)
- Git
- Stabiilne internet (PDF-allalaadimise samm)
- `.env` fail (`cp .env.example .env`)

---

## 1. Keskkond ja konteinerid

```bash
cp .env.example .env

# Kõik teenused (sh Airflow). Ilma Airflow'ta: docker compose up -d --build db python dbt superset
docker compose up -d --build

docker compose ps
```

Esimakordsel Airflow käivitusel (võtab mõne minuti):

```bash
docker compose up airflow-init
docker compose up -d airflow-api-server airflow-scheduler airflow-dag-processor
```

Kui kasutad ülal `docker compose up -d --build`, käivitatakse `airflow-init` automaatselt.

---

## 2. Andmete laadimine (Python)

### Kohustuslik järjekord

```bash
# JSON allalaadimine → data/raw/case-data-M.json
docker compose exec python python ingestion/download_json.py

# Raw skeema + raw.decisions tabel
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql

# Kontroll: raw.decisions
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name;"

# JSON → raw.decisions
docker compose exec python python ingestion/load_decisions.py

# raw.decision_hits tabel
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql

# Kontroll: raw.decisions + raw.decision_hits
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name;"

# PDF-id → märksõnaotsing → raw.decision_hits (võtab tunde; katkestuse korral jätkub uuesti käivitamisel pdfProcessedAt järgi)
docker compose exec python python ingestion/load_decision_hits.py
```

### PDF töötlemise variandid

Vaikimisi `REQUEST_DELAY_SECONDS=0` (pdf-d laetakse järjest). Kui tekib palju `download` vigu, proovi pausiga või töötle ainult veaga read:

```bash
# Paus PDF-ide vahel (nt 1 s)
docker compose exec -e REQUEST_DELAY_SECONDS=1 python python ingestion/load_decision_hits.py

# Ainult N järgmist töötlemata PDF-i (asenda 5)
docker compose exec -e TEST_LIMIT=5 python python ingestion/load_decision_hits.py

# Uuesti ainult allalaadimise veaga read
docker compose exec -e RETRY_DOWNLOAD_ERRORS=1 -e REQUEST_DELAY_SECONDS=2 python python ingestion/load_decision_hits.py
```

---

## 3. Analüüs ja kontroll (valikuline)

Need skriptid **ei kuulu** automaatsesse pipeline'i; kasulikud arenduses ja kvaliteedi kontrollis.

**Kõik järjest** (sama järjekord mis allpool; peatub esimesel veal):

```bash
docker compose exec python python analysis/run_all.py
```

Eeldab: `download_json` → `load_decisions` → `load_decision_hits` → `dbt run` (mart- ja grain-skriptide jaoks).

Valikuline `ROW_LIMIT` `query_decision_hits_sample.py` jaoks:

```bash
docker compose exec -e ROW_LIMIT=5 python python analysis/run_all.py
```

**Üksikud skriptid:**

```bash
# JSON-i struktuur
docker compose exec python python analysis/inspect_json.py

# Üks näidisrida raw.decisions (esimene decision_id järgi)
docker compose exec python python analysis/query_decisions_sample.py

# decision_hits tabelist soovitud arvu ridade pärimine
docker compose exec -e ROW_LIMIT=5 python python analysis/query_decision_hits_sample.py

# PDF töötlemise ja tabamuste kokkuvõte → summarize_decision_hits_output.json
docker compose exec python python analysis/summarize_decision_hits.py

# Tabamustega ridade JSON fail data\processed\decision_hits.json
docker compose exec python python analysis/export_decision_hits_json.py

# raw.decision_hits CSV-na data\processed\decision_hits.csv (eelda load_decision_hits)
docker compose exec python python analysis/export_decision_hits_csv.py

# Mart tabel CSV-na data\processed\mart_arbitration_decisions.csv (eelda dbt run)
docker compose exec python python analysis/export_mart_arbitration_decisions_csv.py

# Kuupäevade väärtuste olemasolu kontroll JSON-is ja raw.decisions tabelis
docker compose exec python python analysis/summarize_date_fields.py

# Manuse vs otsuse tase (tabamuste arvutamise kontroll pärst dbt käivitamist)
docker compose exec python python analysis/check_decision_grain.py

# Unikaalsuse kontroll (link + metadataReference)
docker compose exec python python analysis/check_attachment_link_ref_uniqueness.py
```

---

## 4. dbt

Käivita pärast jaotist 2. Mudelid ilmuvad Postgresi skeemidesse **`staging`**, **`intermediate`**, **`marts`**.

**Mudelid:** `stg_decisions`, `stg_decision_hits` → `int_relevant_decisions`, `int_decisions_with_hits` → `mart_arbitration_decisions`

### Kohustuslik järjekord

```bash
# 1. Kõik mudelid (staging + intermediate + marts)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --profiles-dir ."

# 2. Testid
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt test --profiles-dir ."
```

### Kihtide kaupa (arenduses jooksul)

```bash
# Ainult staging
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select staging --profiles-dir ."

# Ainult intermediate (eeldab staging)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select intermediate --profiles-dir ."

# Ainult marts (eeldab intermediate)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select marts --profiles-dir ."

# Üks mudel
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select mart_arbitration_decisions --profiles-dir ."

# Süntaks kontroll (kontrollib ilma käivitamiseta, kas dbt projekti failid ja ülesehitus on korras)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt parse --profiles-dir ."
```

### Kontroll pärast dbt run

```bash
# Skeemid, vaated ja tabelid
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema IN ('staging', 'intermediate', 'marts')
ORDER BY table_schema, table_name;"

# Relevantsed PDF-id ja tabamused (attachment taseme granulaarsus)
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) AS relevant_attachments,
  COUNT(*) FILTER (WHERE has_keyword_hit) AS with_keyword_hit
FROM intermediate.int_decisions_with_hits;"

# Relevantsed otsused, tabamused ja osakaal (decision taseme granulaarus)
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) AS relevant_decisions,
  COUNT(*) FILTER (WHERE has_keyword_hit) AS decisions_with_hit,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE has_keyword_hit) / NULLIF(COUNT(*), 0),
    2
  ) AS hit_share_pct
FROM marts.mart_arbitration_decisions;"
```

---

## 5. Andmebaas

```bash
# PostgreSQL interaktiivne käsurea klient (psql) db-konteineris.
# Avab sessiooni andmebaasiga eu-merger-arbitration; saad käivitada SQL-päringuid
# otse terminalis (nt SELECT * FROM marts.mart_arbitration_decisions LIMIT 5;).
# Skeemid: raw, staging, intermediate, marts. Väljumine: \q
docker compose exec db psql -U user -d eu-merger-arbitration

# Näide: tabamuste arv
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT COUNT(*) FROM raw.decision_hits;"

# Näide: PDF töötlemise olek
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) FILTER (WHERE \"pdfProcessedAt\" IS NULL) AS pending,
  COUNT(*) FILTER (WHERE \"pdfProcessingError\" IS NULL AND \"pdfProcessedAt\" IS NOT NULL) AS ok,
  COUNT(*) FILTER (WHERE \"pdfProcessingError\" LIKE 'download:%') AS download_errors
FROM raw.decisions WHERE \"isActive\" = TRUE;"
```

---

## 6. Superset

Apache Superset **6.0.0** (`Dockerfile.superset` — lean image + `psycopg2-binary`). Superset'i enda metadata on SQLite'is; andmed tulevad olemasolevast Postgresist (`marts`).

**Eeldab:** jaotis 4 on tehtud (`mart_arbitration_decisions` olemas).

```bash
# Käivita Superset (esimene kord võtab aega — image allalaadimine + init)
docker compose up -d superset

# Logid (oota kuni "Starting Superset on http://localhost:8088")
docker compose logs -f superset
```

Ava brauseris: **http://localhost:8088**  
Vaikimisi login: `admin` / `admin` (muuda `.env` failis `SUPERSET_ADMIN_*`).

### Andmebaasi ühendus Supersetis

1. ** '+' dropdown → Data → Connect database →**
2. Vali **PostgreSQL**
3. Vali **Connect this database with a SQLAlchemy URI string instead** (Docker-võrk, mitte localhost):

   ```
   postgresql+psycopg2://user:user@db:5432/eu-merger-arbitration
   ```

4. **Test connection** → **Connect**

### Dashboardi ZIP import

Skript impordib `docs/dashboard/` kaustast **uusima** `.zip` faili Superset REST API kaudu (sama sisu mis UI import).

**Eeldab:** Superset töötab ja `mart_arbitration_decisions` on olemas.

```bash
docker compose exec python python superset/import_dashboard.py
```

Skript loeb `.env`-ist `SUPERSET_ADMIN_*` ja `POSTGRES_PASSWORD`. Ava seejärel **http://localhost:8088** → **Dashboards**.

Käsitsi (ilma skriptita): **Settings → Import dashboards** → `docs/dashboard/dashboard_export_20260605.zip` → parool `POSTGRES_PASSWORD` (vaikimisi `user`).

### Dataset ja chart

1. ** '+' dropdown → Data → Create Dataset** → vali ühendus → skeem **`marts`** → tabel **`mart_arbitration_decisions`**
2. **Charts → + Chart** → vali dataset
3. Lisa filter **`decision_adoption_date`** (Time range)
4. Näiteks **Big Number**: metric `COUNT(*)`, filter perioodil
5. Teine chart: `COUNT(*)` where `has_keyword_hit = true`, või **Table** / **Pie** sektori järgi

---

## 7. Airflow

Airflow on `compose.yml` failis (`airflow-postgres`, `airflow-init`, `airflow-api-server`, `airflow-scheduler`, `airflow-dag-processor`). DAG-id on repost kaustas `airflow/dags/`. Airflow'i **metadata** on eraldi Postgresis (`airflow-postgres`); pipeline'i andmed on endiselt teenuses `db` (port **5434**).

**Eeldab:** `.env` sisaldab `AIRFLOW_*` väärtusi (vaata `.env.example`).

### Install ja init (esimene kord)

```bash
# Pärast Airflow pildi uuendamist ehita kõik Airflow teenused uuesti
docker compose build airflow-init airflow-api-server airflow-scheduler airflow-dag-processor

# 1. Metastore + admin kasutaja (ühekordne samm; oota kuni konteiner lõpetab)
docker compose up airflow-init

# 2. UI ja scheduler
docker compose up -d airflow-api-server airflow-scheduler airflow-dag-processor

# Logid (oota kuni api-server on terve)
docker compose logs -f airflow-api-server
```

Või käivita ühe käsuga koos ülejäänud stackiga:

```bash
docker compose up -d --build
```

### UI ja login

- Aadress: **http://localhost:8080**
- Login: `.env` → `AIRFLOW_ADMIN_USER` / `AIRFLOW_ADMIN_PASSWORD` (vaikimisi `admin` / `admin`)

### Pipeline DAG-id

| DAG | Kasutus |
|-----|--------|
| **`eu_merger_arbitration`** | **Põhi-DAG** — esimesel käivitusel loob `raw` tabelid kui puuduvad; hiljem uuendab andmeid ja töötleb uued PDF-id. Käivitamise aeg määratud `config\airflow_schedule.txt` |
| **`eu_merger_arbitration_test`** | Test — `TEST_LIMIT=100` PDF-id + init (valikuline enne põhi-DAG-i) |

### Airflow peatamine (ülejäänud stack jääb käima)

```bash
docker compose stop airflow-api-server airflow-scheduler airflow-dag-processor
```

### Airflow metastore nullist (kustutab Airflow'i DB ja logid)

```bash
docker compose down
docker volume rm eu-merger-arbitration-airflow-pg
docker compose up airflow-init
docker compose up -d airflow-api-server airflow-scheduler airflow-dag-processor
```

---

## 8. Konteinerite peatamine

```bash
docker compose down
```

---

## 9. Nullist alustamine

### Täielik reset (Postgresi maht kustub)

```bash
docker compose down -v

# Valikuline: kustuta kohalik JSON ja analüüsi väljundid (Windows PowerShell)
# Remove-Item -Force data/raw/case-data-M.json -ErrorAction SilentlyContinue
# Remove-Item -Force scripts/analysis/*_output.txt, scripts/analysis/summarize_decision_hits_output.json -ErrorAction SilentlyContinue

docker compose up -d --build
docker compose ps
```

Seejärel korda **jaotis 2** samm-sammult, seejärel **jaotis 4** (dbt).

### Ainult raw tabelite tühjendamine (konteinerid jäävad käima)

```bash
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql
docker compose exec python python ingestion/load_decisions.py
docker compose exec python python ingestion/load_decision_hits.py
```

`create_raw_schema.sql` kustutab enne `raw.decision_hits`, seejärel `raw.decisions`.

---
