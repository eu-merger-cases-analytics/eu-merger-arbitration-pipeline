# Edenemisraport

## Mis on valmis

### Dokumentatsioon
- [`README.md`](../README.md) — projekti ülevaade, stack, põhijuhised Dockeri käivitamiseks.
- [`docs/architecture.md`](architecture.md) — äriküsimus, mõõdikud, andmeallikas, andmevoog, kihid, riskid.
- [`docs/data_pipeline.md`](data_pipeline.md) — detailne andmevoo kirjeldus.

### Infrastruktuur
- [`Dockerfile.python`](../Dockerfile.python), [`Dockerfile.dbt`](../Dockerfile.dbt), [`Dockerfile.airflow`](../Dockerfile.airflow), [`compose.yml`](../compose.yml).
- [`config/keywords.txt`](../config/keywords.txt) — vahekohtu otsisõnad EL keeltes.
- [`scripts/requirements.txt`](../scripts/requirements.txt) — `requests`, `psycopg2-binary`, `pdfplumber`.

### Algandmete laadimine ja töötlemine (Python)
- [`download_json.py`](../scripts/ingestion/download_json.py) — JSON allalaadimine `data/raw/case-data-M.json`, valideerimine, katkestuskaitse.
- [`inspect_json.py`](../scripts/analysis/inspect_json.py) — JSON faili ülevaade (`inspect_json_output.txt`).
- [`init/create_raw_schema.sql`](../init/create_raw_schema.sql) — skeem `raw`, tabel `raw.decisions` (karkass + jälgimisveerud).
- [`load_decisions.py`](../scripts/ingestion/load_decisions.py) — JSON → `raw.decisions`:
  - dünaamiline veergude lisamine JSON struktuuri põhjal;
  - upsert ja väljade muutuste logimine;
  - kadunud PDF-ide tuvastamine (`isActive`, `removedDetectedAt`);
  - kaitse mass-deaktiveerimise vastu.
- [`init/create_raw_decision_hits.sql`](../init/create_raw_decision_hits.sql) — tabel `raw.decision_hits` (võtme-, tabamus- ja jälgimisveerud).
- [`load_decision_hits.py`](../scripts/ingestion/load_decision_hits.py) — PDF-id → märksõnaotsing → `raw.decision_hits`:
  - loeb `raw.decisions` tabelist töötlemata PDF-id (`pdfProcessedAt IS NULL`, `isActive = TRUE`);
  - otsib märksõnu `config/keywords.txt` järgi vastavalt `att_attachmentLanguage` väärtusele;
  - salvestab tabamused `raw.decision_hits` (metaandmed kopeeritakse `raw.decisions` tabelist);
  - uuendab `raw.decisions` veeru `pdfProcessedAt` igal PDF-il (ka ilma tabamuseta).
  
### dbt
  - `sources` (`raw.decisions`, `raw.decision_hits`);
  - `models/staging/` — `stg_decision_hits`, `stg_relevant_decisions`;
  - `models/intermediate/` — kuupäevad, NACE, joinid, kvaliteet, selekteeritakse 6(1)(b) ja 8(2) otsused.
  - `models/marts/` — dashboardi mõõdikud.  

### Superset
  - seadistatud testimiseks.
  - loodud dashboard, docs\dashboard\dashboard_export_20260602.zip.

### Airflow
  - ajastamine (download → load_decisions → load_decision_hits → dbt → csv failid).

---

