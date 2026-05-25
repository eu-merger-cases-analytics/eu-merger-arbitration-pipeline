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

docker compose up -d --build

#Oota ~2–3 minutit, kuni kõik teenused on käivitunud
docker compose ps   # kõik peaksid olema "running" või "healthy"

# Andmete laadimine
docker compose exec python python ingestion/download_json.py

# Andmete inspekteerimine
docker compose exec python python ingestion/inspect_json.py

```



