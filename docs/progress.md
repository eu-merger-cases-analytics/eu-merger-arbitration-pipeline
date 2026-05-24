# Edenemisraport

## Mis on valmis

- Loodud projekti esialgne struktuur.
- [`README.md`](../README.md) failis on ülevaade projektist ja kasutatavatest tehnoloogiatest.
- [`docs/images/architecture.md`](architecture.md) failis on kirjeldatud äriküsimus, mõõdikud, andmeallikas, andmevoog, andmebaasi kihid, riskid, privaatsus ja turve.
- Loodud [`Dockerfile.python`](../Dockerfile.python).
- Loodud [`compose.yml`](../compose.yml).

## Järgmised sammud

- Projekti struktuuri täiendamine:
    - config, data, ingestion jms kaustad, hiljem dbt ja airflow.
    - visuaali loomine lõplikust projekti struktuurist README.md faili.
- Luua config kaust ja failid:
    - otsisõnade leidmiseks: täpsustada märksõnu, et vähendada valepositiivseid tulemusi (praegune kokkulepitud valik annab valepositiivseid), iga keele kohta üks kuni mitu märksõna, mida saab eemaldada ja lisada, pdf failide lugemisel võetakse märksõnad automaatselt vastavalt sellele, mis keeles pdf fail on;
    - andmete uuendamisperioodi määramiseks.
- Andmete allalaadimine, salvestamine ja ülevaade JSON struktuurist:
    - allalaetud andmete fail.
    - tekstifail, mis esitab ülevaate Art. 6(1)(b) või Art. 8(2) otsuste meid huvitavatest väärtustest.
    - faili uuendamise protsess, uute koondumiste lisandumise jälgimine.
- Vastavate kriteeriumide alusel välja selekteeritud pdf failide läbilugemine ja otsisõnu sisaldavate otsuste kokku lepitud metaandmete salvestamine:
    - raw faili loomine, hinnanguliselt võtab aega 1-2 tundi.
    - kuidas protsess jätkub katkestuse korral.
    - kuidas toimub andmete uuendamisel valik, millised pdf-d tuleb uuesti lugeda.
    - uute pdf-de lugemine.
- dbt kihtide loomine.
- Airflow seadistamine.
- Dashboardi loomine (otsustame hiljem, kas kasutame Superset või Streamlit või midagi muud).
- requirements.txt faili jooksev täiendamine vastavalt kasutatud teekidele.
- docker failide muutmine/lisamine vastavalt kasutatud tehnoloogiatele.