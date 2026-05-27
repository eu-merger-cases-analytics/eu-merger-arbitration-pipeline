# Vahekohtumehhanismid Euroopa Komisjoni koondumisotsustes

Alates 2000. aastate algusest on Euroopa Komisjon oma tingimuslikes koondumisotsustes kasutanud vahekohtuklausleid. Nende puhul on võimalik, et koondunud ettevõtte kohustuste jõustamine ei ole tegelikkuses konkurentide jaoks võimalik või viib kuluka protsessini.  

Antud projekt ehitab Euroopa Komisjoni avalike koondumisotsuste andmestiku põhjal andmevoo vahekohtuklauslite statistika kuvamiseks dashboardile.  

## Äriküsimus
  
Mitmes vaadeldava perioodi Euroopa Komisjoni tingimuslikus koondumisotsuses on kaalutud tingimuste jõustamiseks vahekohtumehhanismi ning milline on selliste otsuste sektoraalne jaotuvus ja trend (NACE-koodide alusel).  

Kasu tõuseb: 

•	teadlastele, kuna seda andmestikku sellise granulaarsusega seni ei eksisteeri (tuleb sadu pdfe käsitsi avada ja analüüsida); 

•	investoritele investeeringut plaanides riskide hindamiseks (nt kas tingimuste üle tekkivad vaidlused on pigem avalikud või konfidentsiaalsed; kas võimalik vaidluste lahendamise mehhanism ise võib olla Euroopa õigusega vastuolus);

•	turuosalistele, sh VKE-dele, Komisjoni koondumismenetluse raames turu-uuringule vastates vaidluste lahendamise mehhanismi osas teadlike valikute tegemiseks; 

•	regulaatoritele hindamaks vahekohtuklauslite kasutamise sagedust ja selle praktika võimaliku muutmise eeldatavat mõju kogu Euroopa turule ja selle eri sektoritele.

**Mõõdikud:**

1. Kalendrikuu või slideriga valitud muu perioodi tingimuslikult heakskiitvates koondumisotsustes vahekohtumehhanismi mainimine, jah/ei näitaja.  
2. Vahekohtumehhanismi mainivate otsuste koguarv ja osakaal kõigist tingimuslikult heakskiitvatest otsustest kuude/aastate lõikes.  
3. Millistes NACE tegevusalades on kaalutud vahekohtumehhanismi?  
4. Milline on trend tegevusalati kuude/aastate/muu valitud perioodi lõikes?  


## Arhitektuur

<p align="center">
  <img src="docs/images/architecture.png" width="800">
</p>

Täpsem kirjeldus: [`docs/architecture.md`](docs/architecture.md)


## Andmestik

| Allikas | Tüüp | Uuendamine | Roll |
|---------|------|--------------|------|
| https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com/case-data-M.json |JSON | Uueneb otsuste/info lisandumisel (tavaliselt iga kuu) | Algallikas |


## Stack

| Komponent | Tööriist |
|-----------|---------|
| Sissevõtt | Python |
| Transformatsioon | dbt Core 1.10 |
| Andmehoidla | PostgreSQL (pgDuckDB) |
| Näidikulaud | Apache Superset 6.x (või Streamlit) |
| Orkestreerimine | Apache Airflow 3.x  |


## Käivitamine
```bash

# Keskkonna seadistamine
cp .env.example .env

# onteinerite käivitamine
docker compose up -d --build

# Kontroll, et kõik konteinerid jooksevad
docker compose ps   # db peaks olema "healthy", python ja dbt "running"

# Andmete allalaadimine
docker compose exec python python ingestion/download_json.py

# JSON-i struktuuri uurimine
docker compose exec python python ingestion/inspect_json.py

# PDF-ide töötlemine ja vahekohut kaaluvate otsuste leidmine
docker compose exec python python ingestion/ingest.py

# Tulemused salvestatakse:
#   data/processed/arbitration_hits.jsonl        — masinloetav, dbt jaoks
#   data/processed/arbitration_hits_readable.json — inimloetav, ülevaatamiseks
#   logs/ingest_summary.json                      — statistika

# dbt käivitamine
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt debug --profiles-dir ."

# dbt testid
docker compose exec dbt bash -c "cd eu_merger_arbitration && dbt test --profiles-dir ."

# Staging schema ja tabeli loomine SQL-is
docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_staging_schema.sql

# Andmete laadimine staging tabelisse
docker compose exec python python ingestion/load_to_staging.py

# Andmebaasi sisselogimine
docker compose exec db psql -U user -d eu-merger-arbitration

# Staging andmete kontroll
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT COUNT(*) FROM staging.arbitration_hits;"
docker compose exec db psql -U user -d eu-merger-arbitration -c "SELECT * FROM staging.arbitration_hits LIMIT 5;"
```



