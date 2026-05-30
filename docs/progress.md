# Edenemisraport

## Mis on valmis

### Dokumentatsioon
- [`README.md`](../README.md) — projekti ülevaade, stack, põhijuhised Dockeri käivitamiseks.
- [`docs/architecture.md`](architecture.md) — äriküsimus, mõõdikud, andmeallikas, andmevoog, kihid, riskid.
- [`docs/data_pipeline.md`](data_pipeline.md) — detailne andmevoo kirjeldus.

### Infrastruktuur
- [`Dockerfile.python`](../Dockerfile.python), [`Dockerfile.dbt`](../Dockerfile.dbt), [`compose.yml`](../compose.yml).
- [`config/keywords.txt`](../config/keywords.txt) — vahekohtu otsisõnad EL keeltes.
- [`scripts/requirements.txt`](../scripts/requirements.txt) — `requests`, `psycopg2-binary`, `pdfplumber`.

### Algandmete laadimine ja töötlemine (Python)
- [`init/create_raw_schema.sql`](../init/create_raw_schema.sql) — skeem `raw`, tabel `raw.decisions` (karkass + jälgimisveerud).
- [`download_json.py`](../scripts/ingestion/download_json.py) — JSON allalaadimine `data/raw/case-data-M.json`, valideerimine, katkestuskaitse.
- [`inspect_json.py`](../scripts/analysis/inspect_json.py) — arenduslik JSON-i ülevaade (`inspect_json_output.txt`).
- [`load_decisions.py`](../scripts/ingestion/load_decisions.py) — JSON → `raw.decisions`:
  - dünaamiline veergude lisamine JSON struktuuri põhjal;
  - upsert ja väljade muutuste logimine;
  - kadunud PDF-ide tuvastamine (`isActive`, `removedDetectedAt`);
  - kaitse mass-deaktiveerimise vastu.

### dbt
- dbt projekt initsialiseeritud (`dbt/eu_merger_arbitration/`).
- Tegelikud ärimudelid **puuduvad**.

---

## Järgmised sammud

**Loo `init/create_raw_decision_hits.sql`** — tabel `raw.decision_hits`.  
**Implementeeri `load_decision_hits.py`**:
   - loe `raw.decisions`-st Art. `6(1)(b)` / `8(2)` töötlemata PDF-id;
   - otsi märksõnu `config/keywords.txt` järgi;
   - salvesta tabamused `raw.decision_hits`;
   - uuenda `pdfProcessedAt` igal PDF-il (ka ilma tabamuseta).  

**dbt mudelid**:
   - `sources` (`raw.decisions`, `raw.decision_hits`);
   - `models/staging/` — `stg_decision_hits`, `stg_relevant_decisions`;
   - `models/intermediate/` — kuupäevad, NACE, joinid, kvaliteet;
   - `models/marts/` — dashboardi mõõdikud.  

**Uuenda README** — täielik käivitamise järjekord vastavalt `data_pipeline.md`.  

**Uuenda [`docs/architecture.md`](architecture.md)**- andmebaasi kihtide kirjeldus võib vajada uuendamist vastavalt `data_pipeline.md`-le.  

**Airflow** — ajastamine (download → load_decisions → load_decision_hits → dbt).  

**Dashboard** — Superset või Streamlit, seotud dbt mart tabelitega.  

---

## Takistused ja riskid

| Takistus / risk | Mõju | Võimalik maandus |
|-----------------|------|------------------|
| PDF töötlemine on aeglane (~3 h täismahus) | Pipeline viibib; arendus/testimine aeglane | `TEST_LIMIT`; eraldi Airflow samm; resume `pdfProcessedAt` kaudu |
| EC JSON struktuuri muutused | `load_decisions` võib jätta veerud/väärtused puudu | Dünaamiline schema + hoiatused; `inspect_json.py` perioodiline kontroll |
| Märksõnade täpsus | Valepositiivsed / valenegatiivsed | `keywords.txt` kontroll |
