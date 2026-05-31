# Andmevoo detailne kirjeldus

## Ülevaade

```
Andmete laadimine (Python):
  → download_json.py
  → data/raw/case-data-M.json
  → inspect_json.py → inspect_json_output.txt [valikuline, ei pea olema automatiseeritud andmevoo osa]

Toorandmete töötlemine (Python, SQL):
  → create_raw_schema.sql
  → tabel raw.decisions
  → load_decisions.py
      (laeb JSON-ist andmebaasi kõigi juhtumite kõigi otsuste kõik metaandmed;
      1 rida = 1 unikaalne attachmentLink + att_metadataReference; case/decision väljad korduvad.
      Võib olla üksikuid juhtumeid, kus sama metadatareference'iga sama pdf faili on topelt — neid käsitleme veana, andmebaasi salvestatakse viimane pdf.)
  → create_raw_decision_hits.sql
  → tabel raw.decision_hits
  → load_decision_hits.py
      (töötleb raw.decisions tabelist otsuste PDF-id;
      kirjutab raw.decision_hits tabelisse ainult märksõnaga vastete kõik metaandmed)
  → summarize_decision_hits.py → summarize_decision_hits_output.json [valikuline, ei pea olema automatiseeritud andmevoo osa]

Analüütika (dbt):
  → dbt staging (view) — minimaalne puhastus allikast
  → dbt intermediate (view) — äriloogika (kuupäevad, NACE, joinid, kvaliteet), selekteeritakse välja Art. `6(1)(b)` / `8(2)` otsused
  → dbt marts (tabel) — dashboardi mõõdikud
  → dashboard (Superset / Streamlit)
```

**Nimetamine:** Postgres skeemi nime `staging` ei kasutata, et ei oleks sama dbt staging kihiga. Mõlemad Pythoni väljundid jäävad `raw` skeemi alla. Vana nimi `load_to_staging.py` on asendatud nimega `load_decision_hits.py`.

---

## Init SQL

### [`create_raw_schema.sql`](../init/create_raw_schema.sql)
Loob skeemi `raw` ja tabeli `raw.decisions` karkassi (lisab tabelisse attachmentLink + att_metadataReference ja jälgimisveerud, mida json andmetes ei ole).

- Unikaalne võti: `attachmentLink + att_metadataReference` - unikaalne igale reale (topelt esinemist käsitleme veana andmetes), case ja decision metaandmed korduvad
- Jälgimisveerud lisatakse tabeli loomisel, nende sisu lisatakse andmete laadimisel Pythoni skriptidega, mitte JSON-failist nagu juhtumi/otsuse andmed:
  - `pdfProcessedAt` — kas PDF on `load_decision_hits.py` poolt töödeldud (`NULL` = töötlemata)
  - `decision_id` — surrogate primary key (`SERIAL`)
  - `isActive` — kas manus on andmete uuendamisel JSON-is endiselt olemas (`FALSE` = kadunud)
  - `removedDetectedAt` — millal kadumine tuvastati
  - `loadedAt` — rea esimene laadimise aeg
  - `lastCheckedAt` — viimati `load_decisions.py` poolt kontrollitud
  - `pdfProcessingError` — PDF töötlemise viga (genereerib `load_decision_hits.py`; `NULL` = viga puudub)
- Ülejäänud andmeveerud lisab `load_decisions.py` dünaamiliselt JSON-i struktuuri põhjal

### [`create_raw_decision_hits.sql`](../init/create_raw_decision_hits.sql)
Loob tabeli `raw.decision_hits` (märksõnale vastanud PDF-id). Käivita pärast `create_raw_schema.sql` ja `load_decisions.py`.

- Metaandmeveerud (`case_*`, `dec_*`, `att_*` jne) lisab `load_decision_hits.py` dünaamiliselt, kopeerides `raw.decisions` tabelist
- `decision_id` — viide lähte reale `raw.decisions`
- Unikaalne võti: `(att_attachmentLink, att_metadataReference)` ja `decision_id` (üks tabamus = üks manus, ühe case kohta võib olla mitu otsust, ühel otsusel võib olla mitu pdf faili)
- Tabamuse veerud (`load_decision_hits.py` täidab need PDF-i otsingu tulemusena):
  - `matchedKeywords` — kõik leitud unikaalsed märksõnad, eraldatud ` | `
  - `matchedLanguage` — millise keele reegleid kasutati
  - `matchContext` — PDF-i tekstilõik (~100 tähemärki enne ja pärast) dokumendi **kõige varasema** tabamuse ümbruses
  - `loadedAt` — millal tabamus andmebaasi salvestati

---

## Skriptid

### [`download_json.py`](../scripts/ingestion/download_json.py)
Laeb EU Komisjoni koondumisotsuste JSON faili kettale: `data/raw/case-data-M.json`.

- Kui andmebaasi laadimine katkeb, saab uuesti käivitada ilma uue allalaadimiseta
- `inspect_json.py` ja `load_decisions.py` loevad seda faili
- Airflow saab allalaadimise ja laadimise teha eraldi sammudena

**Katkestuskaitse:** andmed kirjutatakse ajutisse `.tmp` faili. Enne asendamist valideeritakse — `json.load()` peab õnnestuma ja failis peab olema vähemalt 1000 juhtumit. Kui valideerimine ebaõnnestub, kustutatakse `.tmp` fail ja olemasolev fail jääb puutumata.

**Uuendamine:** igal käivitamisel laetakse fail uuesti alla ja asendatakse olemasolev.

---

### [`inspect_json.py`](../scripts/analysis/inspect_json.py)
Uurib allalaetud faili `data/raw/case-data-M.json` struktuuri ja kvaliteeti enne andmebaasi laadimist. Arendusaegne tööriist (`scripts/analysis/`), **ei pea kuuluma automaatsesse pipeline'i**. Käivita pärast `download_json.py`.

**Sisend:** `data/raw/case-data-M.json`  
**Väljund:** konsool + `scripts/analysis/inspect_json_output.txt` (iga käivitus kirjutab faili üle).  
Statistikat kaasuste kohta, millel on vähemalt üks otsus, mille `decisionTypes` sisaldab `6(1)(b)` või `8(2)`:

---

### [`load_decisions.py`](../scripts/ingestion/load_decisions.py)
Laeb **kõigi** kaasuste **kõik metaandmed** failist `data/raw/case-data-M.json` tabelisse `raw.decisions`.

**Üks rida = üks unikaalne PDF** (`attachmentLink + att_metadataReference`). Case ja decision väljad korduvad, täielik normaliseerimine toimub dbt-s.

**Dünaamiline schema:**
- Tabelisse lisatakse dünaamiliselt veerud JSON faili võtmete alusel.
- Kui JSON struktuuri ilmneb uusi metaandmeid, siis puuduvad veerud lisatakse automaatselt (`ALTER TABLE ADD COLUMN`, `TEXT`)
- Veergude nimedel prefiksid eristamaks, millise andmestruktuuri osa juurde veerg kuulub: `case_*`, `caseAtt_*`, `dec_*`, `att_*`

**Uuendamise loogika:**
- Uued read lisatakse
- Olemasolevaid ridu võrreldakse väli-väljalt; muutused uuendatakse ja logitakse
- Kadunud väljad / uued väljad logitakse
- `lastCheckedAt` uuendatakse igal jooksul (kui protsess katkeb, saab jätkata mitteprotsessitud kirjetega)

**Kadunud PDF-ide tuvastamine:**
- Kui leitakse URL, mis on raw.decisions tabelisse salvestatud, aga uues JSON-is puudub, muudetakse väärtused veergudes `isActive=FALSE`, `removedDetectedAt`
- Kaitse mass-deaktiveerimise vastu: kui linke JSON-ist ei leita, katkestatakse protsess veaga ja ühtegi rida ei märgita kadunuks. Andmebaas jääb eelmisse olekusse.

**Jälgimisveerud:** `decision_id`, `isActive`, `removedDetectedAt`, `loadedAt`, `pdfProcessedAt`, `lastCheckedAt`

---

### [`load_decision_hits.py`](../scripts/ingestion/load_decision_hits.py)
Loeb `raw.decisions` tabelist töötlemata PDF-id, otsib vahekohtu märksõnu ja salvestab **ainult tabamusega otsuste metaandmed** tabelisse `raw.decision_hits`. `raw.decisions`sisaldab kõik manused, `raw.decision_hits` osakaal arvutatakse dbt-s (intermediate).

**Töövoog iga PDF kohta:**
1. Vali read: `pdfProcessedAt IS NULL`, `isActive = TRUE` (pdf pole veel töödeldud ja võrreldes andmebaasi salvestatud andmetega pole laetud json failis pdf kadunud)
2. Lae PDF alla `att_attachmentLink` URL-ilt
3. Otsi tekstist `config/keywords.txt` pdf keelele vastavad märksõnad (`att_attachmentLanguage` / `attachmentLanguage`)
4. Kui märksõna leitud → lisa rida `raw.decision_hits` tabelisse
5. Uuenda `raw.decisions.pdfProcessedAt = NOW()` (**alati**, ka ilma tabamuseta)

**Checkpoint:**
- `pdfProcessedAt IS NULL` → töötlemata
- `pdfProcessedAt IS NOT NULL` → jäetakse vahele
- Katkestuse korral jätkab järgmine käivitus töötlemata ridadega

**Märksõnad (`config/keywords.txt`):**
- Reegel rea kohta: `KEEL: märksõna` (nt `EN: arbitrat*`)
- Kontrollitakse ainult vastava keele märksõnu.

**Salvestatud `raw.decision_hits` veerud:**
- Case- ja decision-metaandmed
- Attachment-metaandmed
- `matchedKeywords` — kõik PDF-is leitud unikaalsed märksõnad (` | ` eraldatud)
- `matchedLanguage` — otsingu keel
- `matchContext` — tekstilõik kõige varasema tabamuse ümbruses (~100 tähemärki enne ja pärast)

**Keskkonnamuutuja:** `TEST_LIMIT=N` — töötleb ainult esimesed N töötlemata PDF-i (testimiseks).

```bash
docker compose exec -e TEST_LIMIT=5 python python ingestion/load_decision_hits.py
```

---

## PDF töötlemise vead

Vead salvestatakse **andmebaasi** (`raw.decisions`). Kokkuvõte on `summarize_decision_hits.py` väljundis.

### Veerg andmebaasis

| Veerg | Tabel | Tähendus |
|-------|-------|----------|
| `pdfProcessedAt` | `raw.decisions` | PDF on töödeldud (`NULL` = töötlemata) |
| `pdfProcessingError` | `raw.decisions` | Vea tekst (`NULL` = edukas allalaadimine ja parsimine) |

Viga ei tähenda, et rida puudub — metaandmed jäävad `raw.decisions` tabelisse, veergu `pdfProcessingError` lisatakse vea tekst. `raw.decision_hits` saab ainult edukalt loetud PDF-idest leitud tabamused.

### Veatüübid (`pdfProcessingError` prefiks)

| Prefiks | Põhjus | Korduskäivitus |
|---------|--------|----------------|
| `download:` | PDF-i allalaadimine ebaõnnestus (võrgu katkestus, aegumine, serveri throttling) | Tuleb uuesti laadida |
| `processing:` | Fail laeti alla, aga pole kehtiv PDF (nt HTML vastus) | Ei — URL/probleem on püsiv |

### Väljundid

**1. Konsool (`load_decision_hits.py`)** — jooksva käivituse kokkuvõte:
```text
Done. Processed: n  |  Hits saved: n  |  Errors: n
```
`Errors` loeb ainult selle käivituse vigu, mitte kogu andmebaasi seisu.

**2. JSON (`summarize_decision_hits.py`)** — plokk `errors` failis `summarize_decision_hits_output.json`:
- `totalErrorAttachments` — vigadega manuste arv kokku
- `downloadErrors` / `processingErrors` — jaotus prefiksi järgi
- `successfulAttachments` — edukalt töödeldud (viga puudub)
- `topErrorMessages` — levinumad veateated (lühendatud)
- `rates.errorRateAllProcessedAttachmentsPct` — vigade osakaal


### Millal võiks uuesti käivitada (kavandamisel)

- Pärast esimest täisjooksu: kui `downloadErrors > 0`, käivita `RETRY_DOWNLOAD_ERRORS=1` stabiilse võrguga.
- Tavapärane `load_decision_hits.py` jätab vahele read, kus `pdfProcessedAt` on juba seatud — seega allalaadimisvigu automaatselt ei proovi uuesti.
- Enne dbt-d: veendu, et töötlemata (`pdfProcessedAt IS NULL`) ja lahendamata `download:` vead on minimaalsed.

---

### [`summarize_decision_hits.py`](../scripts/analysis/summarize_decision_hits.py)
Genereerib kokkuvõtte decision_hits tabelisse salevestatud andmetest [`summarize_decision_hits_output.json`](../scripts/analysis/summarize_decision_hits_output.json) faili (iga käivitus kirjutab faili üle).

---

## dbt mudelid *(kavandamisel)*

dbt **ei** lae JSON-it ega PDF-e uuesti. Allikad on `raw.decisions` ja `raw.decision_hits`.

### dbt staging (`models/staging/`)
Näiteks: `stg_decision_hits`, `stg_relevant_decisions`

- loeb Postgres `raw` tabeleid (`source()` definitsioonid)
- minimaalne puhastus: veerunimed, filtrid

### dbt intermediate (`models/intermediate/`)
Näiteks: `int_decision_hits`, `int_relevant_decisions`

- metaandmete valik
- selekteeritakse välja Art. `6(1)(b)` / `8(2)` otsused
- kuupäevad: `TEXT` → `DATE`
- NACE: koodi ja nimetuse eraldamine
- lisada veerg **numerator:** `raw.decision_hits` (märksõnaga PDF-id)
- lisada veerg **denominator:** `raw.decisions`, filtreeritud Art. `6(1)(b)` / `8(2)` (kõik asjakohased PDF-id, mitte ainult hitid)
- **tabamuse osakaal:** `decision_hits` sisaldab ainult hitte; intermediate joinib `decisions` (töödeldud, relevant) + `LEFT JOIN decision_hits` → `has_keyword_hit`; osakaal = hitid / kõik relevant
- andmekvaliteedi testid

### dbt marts (`models/marts/`)
Näiteks: `mart_arbitration_monthly`, `mart_arbitration_by_sector`

Dashboardi mõõdikud (vt `architecture.md`):
- vahekohtu mainimiste arv kuus/aastas
- osakaal tingimuslikest otsustest (`matched / total relevant`)
- jaotus NACE sektori järgi
- trend ajas sektori kaupa


---

## Dasboard (Apache Superset või Streamlit)  *(kavandamisel)*  


