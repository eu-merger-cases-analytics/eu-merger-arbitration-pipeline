# Edenemisraport
 
## Mis on valmis
 
- [`README.md`](../README.md) - ülevaade projektist ja kasutatavatest tehnoloogiatest, juhised projekti käivitamiseks.
- [`docs/architecture.md`](architecture.md) - kirjeldatud äriküsimus, mõõdikud, andmeallikas, andmevoog, andmebaasi kihid, riskid, privaatsus ja turve.
- [`docs/data_pipeline.md`](data_pipeline.md) - detailne andmevoo kirjeldus koos loogika ja põhjendustega.
- Loodud [`Dockerfile.python`](../Dockerfile.python) ja [`Dockerfile.dbt`](../Dockerfile.dbt).
- Loodud [`compose.yml`](../compose.yml) teenustega: `db` (PostgreSQL/DuckDB), `python`, `dbt`.
- Loodud `config/keywords.txt` — vahekohtu otsisõnad EL keeltes.
- Loodud `init/create_raw_schema.sql` — `raw.decisions` tabeli loomine.
- Loodud `ingestion/` kaust:
  - [`download_json.py`](../scripts/ingestion/download_json.py) — algandmete allalaadimine koos valideerimise ja katkestuskaitsega.
  - [`inspect_json.py`](../scripts/ingestion/inspect_json.py) — algandmete inspekteerimine, tulemused salvestatakse `inspect_json_output.txt`.
  - [`load_decisions.py`](../scripts/ingestion/load_decisions.py) — kõigi otsuste PDF metaandmete laadimine `raw.decisions` tabelisse, upsert loogika ja kadunud PDF-ide tuvastamine.
- dbt projekt loodud (`dbt init`), profiilid seadistatud `env_var()` kaudu.

## Järgmised sammud
 
- Kirjutada uus `load_to_staging.py` — loeb `raw.decisions` tabelist töötlemata PDF-id, otsib märksõnu, salvestab `staging.decision_hits` tabelisse.
- dbt staging, intermediate ja mart mudelite loomine.
- Airflow seadistamine.
- Dashboardi loomine (Superset või Streamlit, otsustame hiljem).
- `requirements.txt` jooksev täiendamine.
- `architecture.png` kontroll, et vastaks tegelikule protsessile.

## Takistused