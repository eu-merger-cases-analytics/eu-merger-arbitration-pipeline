# Andmevoo detailne kirjeldus
 
## Ülevaade
 
```
download_json.py → load_decisions.py → load_to_staging.py → dbt
```
- **raw** — töötlemata algandmed, kõik otsused
- **staging** — ainult Art. `6(1)(b)` ja Art. `8(2)` otsused, mis sisaldavad märksõna
- **dbt intermediate + mart** — puhastatud ja agregeeritud andmed dashboardi jaoks
---
 
## Skriptid
 
### [`download_json.py`](../scripts/ingestion/download_json.py)
Laeb EU lehelt koondumisotsuste JSON faili kettale (mitte mällu):
- Kui andmebaasi laadimine katkeb, saab uuesti käivitada ilma uue allalaadimiseta
- `inspect_json.py` vajab faili
- Airflow saab allalaadimine ja laadimine olla eraldi sammud  
**Katkestuskaitse:** andmed kirjutatakse ajutisse `.tmp` faili. Enne asendamist valideeritakse — `json.load()` peab õnnestuma ja failis peab olema vähemalt 1000 kirjet. Kui valideerimine ebaõnnestub, kustutatakse `.tmp` fail ja olemasolev fail jääb puutumata.
 
**Uuendamine:** igal käivitamisel laetakse fail uuesti alla ja asendatakse olemasolev.
 
---
 
### [`inspect_json.py`](../scripts/ingestion/inspect_json.py)
Algandmete faili `case-data-M.json` inspekteerimine — arendusaegne tööriist, ei kuulu automaatsesse pipeline'i.
 
- Näitab statistikat ainult Art. `6(1)(b)` ja Art. `8(2)` otsuste kohta
- Näitab NACE sektorite jaotust divisjoni tasemel
- Kontrollib, millised väljad sisaldavad rohkem kui ühte väärtust
- Tulemused salvestatakse `inspect_json_output.txt` faili
---
 
### [`load_decisions.py`](../scripts/ingestion/load_decisions.py)
Laeb kõigi otsuste metaandmete valiku JSON failist andmebaasi tabelisse `raw.decisions`.
 
- Filtreerimine toimub järgmises sammus
- Kui hiljem tekib vajadus teiste artiklite järele, andmed on juba olemas  
**Üks rida = üks unikaalne PDF** (`attachmentLink` on unikaalne võti). Case ja otsuse väljad korduvad igal real — normaliseerimine toimub dbt-s.
 
**Upsert loogika:**
- Uued PDF URL-id lisatakse
- Olemasolevad jäetakse puutumata
- `pdfProcessedAt` jääb uutel ridadel `NULL` — märk, et PDF on töötlemata  
**Kadunud PDF-ide tuvastamine:**
- Võrreldakse andmebaasi URL-e uue JSON-i URL-idega
- Kadunud URL-id märgitakse `isActive=FALSE` ja `removedDetectedAt` täidetakse
- Kaitse mass-deaktiveerimise vastu: kui JSON parsimine ei leia ühtegi URL-i, katkestab protsess veateatega  
**Katkestuskaitse:** kogu upsert ja mark_removed toimub ühes transaktsioonis — katkestuse korral andmebaas jääb eelmisesse seisu.  
 
**Võtmete kontroll:** hoiatab, kui JSON struktuur on muutunud (oodatud väljad puuduvad).
 
Salvestatud väljad:
 
| Tasand | Väljad |
|--------|--------|
| Case | `caseNumber`, `caseTitle`, `caseCompanies`, `caseInstrument`, `caseRegulation`, `caseSimplified`, `caseSectors`, `caseInitiationDate`, `caseNotificationDate`, `caseDeadlineDate`, `caseLastDecisionDate`, `caseAttachments` |
| Otsus | `decisionNumber`, `decisionAdoptionDate`, `decisionOfficialJournalPublicationsPublishedDates`, `decisionTypeCode`, `decisionTypeLabel` |
| Attachment | `attachmentMetadataReference`, `attachmentLanguage`, `attachmentLanguageLower`, `attachmentName`, `attachmentLink` |
| Jälgimine | `isActive`, `removedDetectedAt`, `loadedAt`, `pdfProcessedAt` |
 
---
 
### [`load_to_staging.py`](../scripts/ingestion/load_to_staging.py) *(kavandamisel)*
Loeb `raw.decisions` tabelist töötlemata PDF-id, otsib märksõnu ja salvestab otsused, mille pdf-failides esineb märksõna, `staging.decision_hits` tabelisse.
 
**PDF töötlemine iga attachment kohta:**
1. Laeb PDF alla `attachmentLink` URL-ilt
2. Otsib teksti `config/keywords.txt` reeglite järgi — keele kaupa (`attachmentLanguage` põhjal)
3. Kui märksõna leidub, lisatakse rida `staging.decision_hits` tabelisse
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
Andmed tulevad `staging.decision_hits` tabelist. Minimaalne transformatsioon.
 
### Intermediate
- Parsib kuupäevad (`VARCHAR` → `DATE`)
- Normaliseerib NACE sektorikoodid — eraldab koodi ja nimetuse
- Kontrollib andmekvaliteeti (not null, unikaalsus, kuupäevavahemik)
### Mart
Dashboardi jaoks valmis agregaadid:
- Vahekohtu mainimiste arv/osakaal kuus/aastas
- Osakaal kõigist Art. 6(1)(b)/8(2) otsustest (`matchedDecisions / totalRelevantDecisions`)
- Jaotus NACE sektori järgi
- Trend ajas sektori kaupa
 