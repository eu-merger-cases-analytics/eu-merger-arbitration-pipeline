# Andmevoo detailne kirjeldus
 
## Ülevaade
 
```
download_json.py → load_decisions.py → load_to_staging.py → dbt
```
 
- **raw** — töötlemata algandmed, kõik otsused, kõik metaandmed
- **staging** — ainult vahekohtu märksõna sisaldavad `6(1)(b)` ja Art. `8(2)` otsused
- **dbt intermediate + mart** — puhastatud ja agregeeritud andmed dashboardi jaoks
---
 
## Skriptid
 
### [`download_json.py`](../scripts/ingestion/download_json.py)
Laeb EU lehelt koondumisotsuste JSON faili kettale.
 
- Kui andmebaasi laadimine katkeb, saab uuesti käivitada ilma uue allalaadimiseta
- `inspect_json.py` vajab faili
- Airflow saab allalaadimine ja laadimine olla eraldi sammud  
**Katkestuskaitse:** andmed kirjutatakse ajutisse `.tmp` faili. Enne asendamist valideeritakse — `json.load()` peab õnnestuma ja failis peab olema vähemalt 1000 kirjet. Kui valideerimine ebaõnnestub, kustutatakse `.tmp` fail ja olemasolev fail jääb puutumata.
 
**Uuendamine:** igal käivitamisel laetakse fail uuesti alla ja asendatakse olemasolev.
 
---
 
### [`inspect_json.py`](../scripts/ingestion/inspect_json.py)
Algandmete faili `case-data-M.json` inspekteerimine — arendusaegne tööriist, ei kuulu automaatsesse pipeline'i.
 
- Näitab statistikat ainult Art. `6(1)(b)` ja Art. `8(2)` otsuste kohta
- Kontrollib `attachmentLanguage` ja `language` väljade kokkulangevust
- Näitab NACE sektorite jaotust divisjoni tasemel
- Kontrollib, millised väljad sisaldavad rohkem kui ühte väärtust
- Tulemused salvestatakse `inspect_json_output.txt` faili
---
 
### [`load_decisions.py`](../scripts/ingestion/load_decisions.py)
Laeb kõigi otsuste kõik metaandmed JSON failist andmebaasi tabelisse `raw.decisions`.
 
**Üks rida = üks unikaalne PDF** (`att_attachmentLink` on unikaalne võti). Kõik pesastatud tasandid korduvad igal real — normaliseerimine toimub dbt-s.
 
**Dünaamiline schema:**
- Enne laadimist skaneeritakse kõik JSON võtmed kõigil tasanditel (case, caseAttachments, decisions, decisionAttachments)
- Puuduvad veerud lisatakse automaatselt (`ALTER TABLE ADD COLUMN`, kõik `TEXT` tüüpi)
- Veergude nimetamine prefixite lisamisega: `case_*`, `caseAtt_*`, `dec_*`, `att_*`  
**Uuendamise loogika:**
- Uued read lisatakse
- Olemasolevaid ridu võrreldakse väli-väljalt — muutunud väljad uuendatakse ja logitakse
- Kui väli on kadunud (andmebaasis on väärtus, JSON-is `NULL`) — logitakse hoiatus
- Kui väli on lisandunud (andmebaasis `NULL`, JSON-is väärtus) — uuendatakse, logitakse info
- `lastCheckedAt` uuendatakse igal jooksul igale reale  
**Kadunud PDF-ide tuvastamine:**
- Kadunud URL-id märgitakse `isActive=FALSE` ja `removedDetectedAt` täidetakse
- Kaitse mass-deaktiveerimise vastu: kui JSON parsimine ei leia ühtegi URL-i, katkestab protsess veateatega  
**Sisemised jälgimisveerud:** `decision_id`, `isActive`, `removedDetectedAt`, `loadedAt`, `pdfProcessedAt`, `lastCheckedAt`
 
---
 
### [`load_to_staging.py`](../scripts/ingestion/load_to_staging.py) *(kavandamisel)*
Loeb `raw.decisions` tabelist töötlemata PDF-id, otsib märksõnu ja salvestab vasted `staging.decisions_hits` tabelisse.
 
**Miks see samm on eraldi `load_decisions.py`-st:**
- PDF allalaadimine ja teksti otsimine on aeglane (~3 tundi täismahus)
- Metaandmete laadimine on kiire ja sõltumatu PDF töötlemisest
- Airflow saab neid kahte sammu eraldi hallata ja uuesti käivitada
 
**PDF töötlemine iga attachment kohta:**
1. Laeb PDF alla `attachmentLink` URL-ilt
2. Otsib teksti `config/keywords.txt` reeglite järgi — keele kaupa (`attachmentLanguage` põhjal)
3. Kui märksõna leidub, lisatakse rida `staging.decisions_hits` tabelisse
4. Uuendab `raw.decisions` tabelis `pdfProcessedAt = NOW()`
**Checkpoint loogika:**
- `pdfProcessedAt IS NULL` = töötlemata
- `pdfProcessedAt IS NOT NULL` = juba töödeldud, jäetakse vahele
- Katkestuse korral jätkab järgmine käivitus sealt, kus pooleli jäi
**Märksõnade otsimine (`config/keywords.txt`):**
- Iga keel on eraldi reegel: `EN: arbitrat*`, `DE: Schiedsgericht*` jne
- PDF otsitakse ainult selle keele reeglitega, mis on märgitud `attachmentLanguage` väljal
- Kui keele jaoks reegleid pole, jäetakse PDF vahele — ei kasutata fallback keelt
- Metamärk `*` matchi suvalise arvu tähemärkidega
- AND tingimus: `CZ: rozhodč*:řízen*` — mõlemad peavad tekstis esinema
**Salvestatud väljad `staging.hits`:**
- Kõik case ja otsuse metaandmed
- Matched attachment metaandmed
- Märksõna, keel ja kontekstilõik (100 tähemärki enne ja pärast osumit)
---
 
## dbt mudelid *(kavandamisel)*
 
### Staging (view)
Andmed tulevad `staging.decisions_hits` tabelist. Minimaalne transformatsioon.
 
### Intermediate
- Parsib kuupäevad (`VARCHAR` → `DATE`)
- Normaliseerib NACE sektorikoodid — eraldab koodi ja nimetuse
- Kontrollib andmekvaliteeti (not null, unikaalsus, kuupäevavahemik)
### Mart
Dashboardi jaoks valmis agregaadid:
- Vahekohtu mainimiste arv kuus/aastas
- Osakaal kõigist Art. 6(1)(b)/8(2) otsustest (`matchedDecisions / totalRelevantDecisions`)
- Jaotus NACE sektori järgi
- Trend ajas sektori kaupa