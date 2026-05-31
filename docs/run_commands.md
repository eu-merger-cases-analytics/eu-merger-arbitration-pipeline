# Käivitamise käskude täielik nimekiri

Täpsem andmevoo kirjeldus: [`data_pipeline.md`](data_pipeline.md).

Kõik käsud eeldavad, et oled projekti juurkaustas ja Docker Compose konteinerid on üleval (`docker compose up -d --build`).

## Pipeline'i järjekord

| Samm | Jaotis | Mida teeb |
|------|--------|-----------|
| 1 | Keskkond | Docker + `.env` |
| 2 | Andmete laadimine | JSON → `raw.decisions` → PDF-id → `raw.decision_hits` |
| 3 | Analüüs *(valikuline)* | Arenduse ja kvaliteedi kontroll |
| 4 | dbt | `raw` → `staging` → `intermediate` → `marts` |
| 5 | Andmebaas | psql ja näidispäringud |
| 6 | Superset *(valikuline)* | Dashboard test `http://localhost:8088` |

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

docker compose up -d --build

docker compose ps
```

---

## 2. Andmete laadimine (Python)

### Kohustuslik järjekord (esimene täisjooks)

```bash
# JSON allalaadimine → data/raw/case-data-M.json
docker compose exec python python ingestion/download_json.py

# Raw skeema + raw.decisions tabel
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql

# Kontroll: raw.decisions peaks olemas olema
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name;"

# JSON → raw.decisions
docker compose exec python python ingestion/load_decisions.py

# raw.decision_hits tabel
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql

# Kontroll: raw.decisions + raw.decision_hits
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name;"

# PDF-id → märksõnaotsing → raw.decision_hits (võtab tunde; katkestuse korral jätkub pdfProcessedAt järgi)
docker compose exec python python ingestion/load_decision_hits.py
```

### PDF töötlemise variandid

Vaikimisi `REQUEST_DELAY_SECONDS=0` (paus puudub). Kui tekib palju `download:` vigu, proovi pausiga või töötle ainult veaga read:

```bash
# Paus PDF-ide vahel (nt 2 s)
docker compose exec -e REQUEST_DELAY_SECONDS=2 python python ingestion/load_decision_hits.py

# Ainult N järgmist töötlemata PDF-i (asenda 5)
docker compose exec -e TEST_LIMIT=5 python python ingestion/load_decision_hits.py

# Uuesti proovi ainult allalaadimise veaga read
docker compose exec -e RETRY_DOWNLOAD_ERRORS=1 -e REQUEST_DELAY_SECONDS=2 python python ingestion/load_decision_hits.py
```

---

## 3. Analüüs ja kontroll (valikuline)

Need skriptid **ei kuulu** automaatsesse pipeline'i; kasulikud arenduses ja kvaliteedi kontrollis.

```bash
# JSON-i struktuur enne laadimist
docker compose exec python python analysis/inspect_json.py

# Üks näidisrida raw.decisions (esimene decision_id järgi)
docker compose exec python python analysis/query_decisions_sample.py

# decision_hits tabelist soovitud arvu ridade pärimine
docker compose exec -e ROW_LIMIT=5 python python analysis/query_decision_hits_sample.py

# PDF töötlemise ja tabamuste kokkuvõte → summarize_decision_hits_output.json
docker compose exec python python analysis/summarize_decision_hits.py

# Kuupäevade täituvus JSON-is ja raw.decisions-is
docker compose exec python python analysis/summarize_date_fields.py

# Manuse vs otsuse tase (tabamuste arvutamise kontroll)
docker compose exec python python analysis/check_decision_grain.py

# Manuste link + metadataReference kontroll JSON-is
docker compose exec python python analysis/check_attachment_link_ref.py

# Unikaalsuse kontroll (link + metadataReference)
docker compose exec python python analysis/check_attachment_link_ref_uniqueness.py
```

---

## 4. dbt

Käivita pärast jaotist 2. Mudelid ilmuvad Postgresi skeemidesse **`staging`**, **`intermediate`**, **`marts`** (mitte `public_staging`).

**Mudelid:** `stg_decisions`, `stg_decision_hits` → `int_relevant_decisions`, `int_decisions_with_hits` → `mart_arbitration_decisions`

### Kohustuslik järjekord (esimene dbt jooks)

```bash
# 1. Kõik mudelid (staging + intermediate + marts)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --profiles-dir ."

# 2. Testid
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt test --profiles-dir ."
```

### Kihtide kaupa (arenduses)

```bash
# Ainult staging
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select staging --profiles-dir ."

# Ainult intermediate (eeldab staging)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select intermediate --profiles-dir ."

# Ainult marts (eeldab intermediate)
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select marts --profiles-dir ."

# Üks mudel
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt run --select mart_arbitration_decisions --profiles-dir ."

# Süntaks kontroll (ilma käivitamiseta)
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

# Relevant manused ja tabamused (attachment grain)
docker compose exec db psql -U user -d eu-merger-arbitration -c "
SELECT
  COUNT(*) AS relevant_attachments,
  COUNT(*) FILTER (WHERE has_keyword_hit) AS with_keyword_hit
FROM intermediate.int_decisions_with_hits;"

# Relevant otsused, tabamused ja osakaal (decision grain — dashboard)
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
# Interaktiivne psql
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

## 6. Superset (test)

Lihtne ühe-konteineri seadistus. Superset'i enda metadata on SQLite'is; andmed tulevad olemasolevast Postgresist (`marts`).

**Eeldab:** jaotis 4 on tehtud (`mart_arbitration_decisions` olemas).

```bash
# Käivita Superset (esimene kord võtab aega — image allalaadimine + init)
docker compose up -d superset

# Logid (oota kuni "Starting Superset on http://localhost:8088")
docker compose logs -f superset
```

Ava brauseris: **http://localhost:8088**  
Vaikimisi login: `admin` / `admin` (muuda `.env` failis `SUPERSET_ADMIN_*`).

### Andmebaasi ühendus Supersetis (üks kord)

1. **Settings → Database connections → + Database**
2. Vali **PostgreSQL**
3. **SQLAlchemy URI** (Docker-võrk, mitte localhost):

   ```
   postgresql+psycopg2://user:user@db:5432/eu-merger-arbitration
   ```

   (Kasuta `.env` väärtusi, kui need erinevad.)

4. **Test connection** → **Connect**

### Dataset ja chart

1. **Data → Datasets → + Dataset** → vali ühendus → skeem **`marts`** → tabel **`mart_arbitration_decisions`**
2. **Charts → + Chart** → vali dataset
3. Lisa filter **`decision_adoption_date`** (Time range)
4. Näiteks **Big Number**: metric `COUNT(*)`, filter perioodil
5. Teine chart: `COUNT(*)` where `has_keyword_hit = true`, või **Table** / **Pie** sektori järgi

---

## 7. Peatamine

```bash
docker compose down
```

---

## 8. Nullist alustamine

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

## Kiire viide: skriptid

| Skript | Roll | Pipeline |
|--------|------|----------|
| `ingestion/download_json.py` | JSON allalaadimine | Jah |
| `ingestion/load_decisions.py` | JSON → `raw.decisions` | Jah |
| `ingestion/load_decision_hits.py` | PDF + märksõnad → `raw.decision_hits` | Jah |
| `analysis/inspect_json.py` | JSON ülevaade | Ei |
| `analysis/query_decisions_sample.py` | Näidis `raw.decisions` | Ei |
| `analysis/query_decision_hits_sample.py` | Näidis `raw.decision_hits` | Ei |
| `analysis/summarize_decision_hits.py` | Kokkuvõtte JSON | Ei |
| `analysis/summarize_date_fields.py` | Kuupäevade täituvus | Ei |
| `analysis/check_decision_grain.py` | Otsuse vs manuse tase | Ei |
| `analysis/check_attachment_link_ref.py` | Link/ref kontroll | Ei |
| `analysis/check_attachment_link_ref_uniqueness.py` | Unikaalsuse kontroll | Ei |
| `init/create_raw_schema.sql` | `raw.decisions` | Jah |
| `init/create_raw_decision_hits.sql` | `raw.decision_hits` | Jah |
| dbt `dbt run` / `dbt test` | `raw` → `staging` → `intermediate` → `marts` | Jah (pärast jaotist 2) |
