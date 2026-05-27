# Edenemisraport

## Mis on valmis

- [`README.md`](../README.md) - ülevaade projektist ja kasutatavatest tehnoloogiatest, juhised projekti käivitamiseks.
- [`docs/architecture.md`](architecture.md) - kirjeldatud äriküsimus, mõõdikud, andmeallikas, andmevoog, andmebaasi kihid, riskid, privaatsus ja turve.
- Loodud [`Dockerfile.python`](../Dockerfile.python).
- Loodud [`compose.yml`](../compose.yml).
- Loodud config kaust ja  [`keywords.txt`](../config/keywords.txt) erinevates keeltes otsisõnade haldamiseks ja lugemiseks.
- Loodud data ja raw kaust allalaetud json faili salvestamiseks.
- Loodud ingestion kaust:
    - [`download_json.py`](../scripts/ingestion/download_json.py) - algandmete allalaadimine.
    - [`inspect_json.py`](../scripts/ingestion/inspect_json.py) - algandmete inspekteerimine.
    - [`inspect_json_output.txt`](../scripts/ingestion/inspect_json_output.txt) - inspect_json.py tulemuse väljaprint.
    - [`ingest.py`](../scripts/ingestion/ingest.py) - art. 6(1)(b) ja art. 8(2) otsuste pdf failide läbilugemine ja otsisõnu sisaldavate otsuste kohta kokku lepitud metaandmete salvestamine.
    - pdf töötlemise tulemus on salvestatud kausta data/processed, kokkuvõte [`ingest_summary.json`](../logs/ingest_summary.json).


## Järgmised sammud

- dbt kihtide loomine.
- Airflow seadistamine.
- Dashboardi loomine (otsustame hiljem, kas kasutame Superset või Streamlit või midagi muud).
- requirements.txt faili jooksev täiendamine vastavalt kasutatud teekidele.
- Dockeri failide muutmine/lisamine vastavalt kasutatud tehnoloogiatele.
- architecture.png kontroll, et vastaks tegelikule protsessile.
- Visuaali loomine lõplikust projekti struktuurist README.md faili.


## Takistused

- Algandmete korduvlaadimine on aeglane (kogu json fail töödeldakse mälus iga kord uuesti).
- pdf failide esmane töötlemine võtab aega ~3 tundi.
- Otsustada, mis andmeid mis kihis andmebaasi salvestatakse.