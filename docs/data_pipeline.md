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
        1 rida = 1 unikaalne otsuse attachmentLink; case/decision väljad korduvad)
  → create_raw_decision_hits.sql
  → tabel raw.decision_hits
  → load_decision_hits.py
       (töötleb raw.decisions tabelist Art. 6(1)(b) / 8(2) PDF-id;
        kirjutab raw.decision_hits tabelisse ainult märksõnaga vastete kõik metaandmed)

Analüütika (dbt):
  → dbt staging (view) — minimaalne puhastus allikast
  → dbt intermediate (view) — äriloogika (kuupäevad, NACE, joinid, kvaliteet)
  → dbt marts (tabel) — dashboardi mõõdikud
  → dashboard (Superset / Streamlit)
```

**Nimetamine:** Postgres skeemi nime `staging` ei kasutata, sest see seguneb dbt staging kihiga. Mõlemad Pythoni väljundid jäävad `raw` skeemi alla. Vana nimi `load_to_staging.py` on asendatud nimega `load_decision_hits.py`.

---

## Init SQL

### [`create_raw_schema.sql`](../init/create_raw_schema.sql)
Loob skeemi `raw` ja tabeli `raw.decisions` karkassi (lisab tabelisse decision attachment pdf lingi ja jälgimisveerud, mida json andmetes ei ole, näiteks "pdfProcessedAt").

- Ülejäänud andmeveerud lisab `load_decisions.py` dünaamiliselt JSON-i struktuuri põhjal
- Unikaalne võti: `att_attachmentLink` - unikaalne igale reale, case ja decision metaandmed korduvad
- `pdfProcessedAt` — kas PDF on `load_decision_hits.py` poolt töödeldud (`NULL` = töötlemata)

### [`create_raw_decision_hits.sql`](../init/create_raw_decision_hits.sql) *(kavandamisel)*
Loob tabeli `raw.decision_hits` (märksõnale vastanud PDF-id).

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

### [`inspect_json.py`](../scripts/ingestion/inspect_json.py)
Algandmete faili `case-data-M.json` inspekteerimine — arendusaegne tööriist, **ei pea kuuluma automaatsesse pipeline'i**.

- Näitab statistikat ainult Art. `6(1)(b)` ja Art. `8(2)` otsuste kohta
- Kontrollib `attachmentLanguage` ja `language` väljade kokkulangevust
- Näitab NACE sektorite jaotust divisjoni tasemel
- Tulemused: `scripts/ingestion/inspect_json_output.txt`

---

### [`load_decisions.py`](../scripts/ingestion/load_decisions.py)
Laeb **kõigi** juhtumite **kõik metaandmed** failist `data/raw/case-data-M.json` tabelisse `raw.decisions`.

**Üks rida = üks unikaalne PDF** (`att_attachmentLink`). Case ja decision väljad korduvad igal real — täielik normaliseerimine toimub dbt-s.

**Dünaamiline schema:**
- Skaneeritakse JSON võtmed tasanditel: case, caseAttachments, decisions, decisionAttachments. Olemasolevate JSON võtmete alusel geneeritakse tabeli veerud.
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

### [`load_decision_hits.py`](../scripts/ingestion/load_decision_hits.py) *(kavandamisel)*
Loeb `raw.decisions` tabelist töötlemata PDF-id, otsib vahekohtu märksõnu ja salvestab **ainult tabamusega otsuste metaandmed** tabelisse `raw.decision_hits`.

**Töövoog iga PDF kohta:**
1. Vali read: Art. `6(1)(b)` või `8(2)`, `pdfProcessedAt IS NULL`, `isActive = TRUE`
2. Lae PDF alla `att_attachmentLink` URL-ilt
3. Otsi tekstist `config/keywords.txt` reeglitega (`att_attachmentLanguage` / `attachmentLanguage`)
4. Kui märksõna leitud → lisa rida `raw.decision_hits` tabelisse
5. Uuenda `raw.decisions.pdfProcessedAt = NOW()` (**alati**, ka ilma tabamuseta)

**Checkpoint (andmebaasis, mitte eraldi failis):**
- `pdfProcessedAt IS NULL` → töötlemata
- `pdfProcessedAt IS NOT NULL` → jäetakse vahele
- Katkestuse korral jätkab järgmine käivitus töötlemata ridadega

**Märksõnad (`config/keywords.txt`):**
- Reegel rea kohta: `KEEL: märksõna` (nt `EN: arbitrat*`)
- Kontrollitakse ainult vastava keele märksõnu.

**Salvestatud `raw.decision_hits` veerud:**
- Case- ja decision-metaandmed
- Attachment-metaandmed
- `matchedKeywords`, `matchedLanguage`, `matchContext` (kontekst ~100 tähemärki ümber tabamust)

**Keskkonnamuutuja:** `TEST_LIMIT=N` — töötleb ainult esimesed N töötlemata PDF-i (testimiseks).

---

## dbt mudelid *(kavandamisel)*

dbt **ei** lae JSON-it ega PDF-e uuesti. Allikad on `raw.decisions` ja `raw.decision_hits`.

### dbt staging (`models/staging/`)
Näited: `stg_decision_hits`, `stg_relevant_decisions`

- loeb Postgres `raw` tabeleid (`source()` definitsioonid)
- minimaalne puhastus: veerunimed, filtrid, ettevalmistus tüüpideks

### dbt intermediate (`models/intermediate/`)
Näited: `int_decision_hits`, `int_relevant_decisions`

- metaandmete valik
- kuupäevad: `TEXT` → `DATE`
- NACE: koodi ja nimetuse eraldamine
- lisada veerg **numerator:** `raw.decision_hits` (märksõnaga PDF-id)
- lisada veerg **denominator:** `raw.decisions`, filtreeritud Art. `6(1)(b)` / `8(2)` (kõik asjakohased PDF-id, mitte ainult hitid)
- andmekvaliteedi testid

### dbt marts (`models/marts/`)
Näited: `mart_arbitration_monthly`, `mart_arbitration_by_sector`

Dashboardi mõõdikud (vt `architecture.md`):
- vahekohtu mainimiste arv kuus/aastas
- osakaal tingimuslikest otsustest (`matched / total relevant`)
- jaotus NACE sektori järgi
- trend ajas sektori kaupa
