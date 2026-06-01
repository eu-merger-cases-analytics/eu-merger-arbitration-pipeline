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

### Andmebaasi ühendus Supersetis

1. ** '+' dropdown → Data → Connect database →**
2. Vali **PostgreSQL**
3. Vali **Connect this database with a SQLAlchemy URI string instead** (Docker-võrk, mitte localhost):

   ```
   postgresql+psycopg2://user:user@db:5432/eu-merger-arbitration
   ```

4. **Test connection** → **Connect**

### Dataset ja chart

1. ** '+' dropdown → Data → Create Dataset** → vali ühendus → skeem **`marts`** → tabel **`mart_arbitration_decisions`**
2. **Charts → + Chart** → vali dataset
3. Lisa filter **`decision_adoption_date`** (Time range)
4. Näiteks **Big Number**: metric `COUNT(*)`, filter perioodil
5. Teine chart: `COUNT(*)` where `has_keyword_hit = true`, või **Table** / **Pie** sektori järgi

---

## 7. Konteinerite peatamine

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
