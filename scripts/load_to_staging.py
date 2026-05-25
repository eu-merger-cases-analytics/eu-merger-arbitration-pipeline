"""Kommenteeritud näide JSON -> PostgreSQL ETL töövoost.

See skript laadib Euroopa Komisjoni konkurentsijuhtumite (merger) andmed
ühelt veebiaadressilt, eraldab sealt meile vajalikud väljad ja kirjutab
need andmebaasi tabelisse `staging`.

Töövoog liigub kolme sammuna:

- Vastuvõtt (extract): loe JSON veebiaadressilt;
- Töötlus (transform): võta JSON-ist välja õiged väljad ja väldi topeltridu;
- Laadimine (load): kirjuta read tabelisse `staging`.

Kui Python on sulle veel uus, loe faili ülevalt alla.
Iga funktsioon teeb ühe väikese sammu ja `main()` seob need sammud tervikuks.
"""

# `import` toob faili sisse teegid, mida me allpool kasutame.
import os

import psycopg2
import requests

# `execute_values` on abifunktsioon, mis oskab ühe käsuga lisada palju ridu
# korraga. See on tunduvalt kiirem kui iga rida ükshaaval lisada.
from psycopg2.extras import execute_values


# Suurte tähtedega nimi viitab tavaliselt konstandile:
# väärtusele, mida me programmi töö jooksul ei muuda.
# Siit aadressilt laeme JSON-faili konkurentsijuhtumite andmetega.
SOURCE_URL = (
    "https://compcases-open-data-portal-files-prod.s3.eu-west-1.amazonaws.com"
    "/case-data-M.json"
)

# Veergude nimed täpselt selles järjekorras, nagu need tabelis `staging` on.
# Mõned väljanimed JSON-is korduvad eri tasanditel (case / decision / attachment),
# seetõttu lisame korduvatele prefiksi, et need omavahel ei seguneks.
COLUMNS = [
    "caseInstrument",
    "caseNumber",
    "caseRegulation",
    "caseTitle",
    "caseSectors",
    "case_metadataReference",
    "decisionAdoptionDate",
    "decisionNumber",
    "decisionTypes",
    "decisionOfficialJournalPublicationsPublishedDates",
    "decision_metadataReference",
    "decision_language",
    "attachmentLink",
    "attachment_language",
    "attachment_metadataReference",
    "attachmentLanguage",
    "attachmentName",
]


def get_connection():
    """Loo andmebaasiühendus keskkonnamuutujate põhjal.

    Selle funktsiooni tulemus on connection-objekt, mille paneme hiljem
    muutujasse `conn`. Seda ühendust kasutame kõigi SQL-käskude jaoks.
    """

    # `os.environ.get("NIMI", "vaikimisi")` küsib väärtust keskkonnast.
    # Kui seda ei ole, kasutatakse paremal olevat vaikimisi väärtust.
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "db"),
        port=os.environ.get("DB_PORT", "5432"),
        user=os.environ.get("DB_USER", "user"),
        password=os.environ.get("DB_PASSWORD", "user"),
        dbname=os.environ.get("DB_NAME", "eu-merger-arbitration"),
    )


def fetch_case_data():
    """Andmete vastuvõtt: loe konkurentsijuhtumid veebiaadressilt.

    Funktsioon tagastab sõnastiku, kus iga võti on juhtumi number
    (nt "M.2027") ja väärtus on selle juhtumi kõik andmed.
    """

    # `requests.get(...)` teeb veebipäringu ja tagastab Response-objekti.
    # `timeout=300` annab suurele failile piisavalt aega kohale jõuda.
    response = requests.get(SOURCE_URL, timeout=300)

    # Kui server vastas veakoodiga, katkestame töö kohe arusaadava veaga.
    response.raise_for_status()

    # `json()` muudab vastuse Pythoni andmestruktuuriks (siin sõnastikuks).
    data = response.json()

    print(f"- Veebiaadressilt tuli {len(data)} juhtumit (case).")
    return data


def first_value(metadata, key):
    """Võta metadata-väljast väärtus välja.

    JSON-is on iga väärtus loendi sees, nt "caseNumber": ["M.2027"].
    See abifunktsioon võtab loendist väärtuse välja. Kui loend on tühi,
    tagastab tühja stringi. Kui väärtusi on mitu, liidab need kokku.
    """

    # `metadata.get(key, [])` küsib välja väärtust; kui välja pole, annab tühja loendi.
    values = metadata.get(key, [])

    # Tühja loendi puhul tagastame tühja stringi, et hiljem ei tekiks viga.
    if not values:
        return ""

    # `" | ".join(...)` liidab loendi elemendid üheks sõneks, eraldajaks " | ".
    return " | ".join(str(v) for v in values)


def extract_case_fields(metadata):
    """Võta välja juhtumi (case) tasandi väljad ühe sõnastikuna."""

    return {
        "caseInstrument": first_value(metadata, "caseInstrument"),
        "caseNumber": first_value(metadata, "caseNumber"),
        "caseRegulation": first_value(metadata, "caseRegulation"),
        "caseTitle": first_value(metadata, "caseTitle"),
        "caseSectors": first_value(metadata, "caseSectors"),
        # JSON-is on selle välja nimi "metadataReference"; meie nimetame
        # selle ümber, et eristada seda decision- ja attachment-tasandist.
        "case_metadataReference": first_value(metadata, "metadataReference"),
    }


def extract_decision_fields(metadata):
    """Võta välja otsuse (decision) tasandi väljad ühe sõnastikuna."""

    return {
        "decisionAdoptionDate": first_value(metadata, "decisionAdoptionDate"),
        "decisionNumber": first_value(metadata, "decisionNumber"),
        "decisionTypes": first_value(metadata, "decisionTypes"),
        "decisionOfficialJournalPublicationsPublishedDates": first_value(
            metadata, "decisionOfficialJournalPublicationsPublishedDates"
        ),
        "decision_metadataReference": first_value(metadata, "metadataReference"),
        "decision_language": first_value(metadata, "language"),
    }


def extract_attachment_fields(metadata):
    """Võta välja manuse (attachment) tasandi väljad ühe sõnastikuna."""

    return {
        "attachmentLink": first_value(metadata, "attachmentLink"),
        "attachment_language": first_value(metadata, "language"),
        "attachment_metadataReference": first_value(metadata, "metadataReference"),
        "attachmentLanguage": first_value(metadata, "attachmentLanguage"),
        "attachmentName": first_value(metadata, "attachmentName"),
    }


def empty_fields(field_dict):
    """Tee samade võtmetega sõnastik, kus kõik väärtused on tühjad.

    Seda läheb vaja siis, kui mõni tasand puudub (nt juhtumil pole manuseid),
    aga me tahame ikkagi, et kõik veerud reas olemas oleksid.
    """

    return {key: "" for key in field_dict}


def build_rows(data):
    """Töötlus: tee JSON-ist tabeliread ja väldi topeltridu.

    Andmed on pesastatud: iga juhtum (case) sisaldab otsuseid (decisions)
    ja iga otsus võib sisaldada manuseid (attachments).

    Üks rida tabelis vastab ühele manusele. Juhtumi ja otsuse väljad
    korduvad iga manuse real. Et vältida topeltridu sama juhtumi numbriga,
    jätame alles ainult need read, kus manuse link (`attachmentLink`) on olemas.
    """

    # Siia loendisse kogume kõik valmis read.
    rows = []

    # `data.items()` annab meile korraga nii juhtumi võtme kui ka selle andmed.
    for case_key, case in data.items():
        # Juhtumi tasandi väljad on samad kõigi selle juhtumi ridade jaoks.
        case_part = extract_case_fields(case.get("metadata", {}))

        # Kogume selle juhtumi võimalikud read eraldi loendisse.
        case_rows = []

        # Käime läbi kõik selle juhtumi otsused.
        for decision in case.get("decisions", []):
            decision_part = extract_decision_fields(decision.get("metadata", {}))

            # Käime läbi kõik selle otsuse manused.
            for attachment in decision.get("decisionAttachments", []):
                attachment_part = extract_attachment_fields(
                    attachment.get("metadata", {})
                )

                # `{**a, **b, **c}` ühendab mitu sõnastikku üheks.
                # Nii saame ühte ritta kokku case-, decision- ja attachment-väljad.
                case_rows.append({**case_part, **decision_part, **attachment_part})

        # Jäta alles ainult read, kus manuse link on tegelikult olemas.
        # See on see samm, mis väldib topeltridu sama juhtumi numbriga.
        linked_rows = [row for row in case_rows if row.get("attachmentLink")]

        if linked_rows:
            # `extend` lisab loendisse korraga mitu elementi.
            rows.extend(linked_rows)
        else:
            # Kui juhtumil polnud ühtegi manust, jätame siiski alles ühe rea,
            # et juhtumi number andmestikust päriselt välja ei kukuks.
            # Decision- ja attachment-väljad jäävad sellel real tühjaks.
            rows.append(
                {
                    **case_part,
                    **empty_fields(extract_decision_fields({})),
                    **empty_fields(extract_attachment_fields({})),
                }
            )

    return rows


def create_staging_table(conn):
    """Loo tabel `staging`, kui seda veel ei ole.

    Kõik veerud on tekstitüüpi, sest staging kihis hoiame andmeid
    võimalikult algkujul. Tüübiteisendused (nt kuupäevad) saab teha hiljem.
    """

    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS staging (
                "caseInstrument"                                     VARCHAR(255),
                "caseNumber"                                         VARCHAR(255),
                "caseRegulation"                                     VARCHAR(255),
                "caseTitle"                                          VARCHAR(1000),
                "caseSectors"                                        TEXT,
                "case_metadataReference"                             VARCHAR(255),
                "decisionAdoptionDate"                               VARCHAR(50),
                "decisionNumber"                                     VARCHAR(255),
                "decisionTypes"                                      TEXT,
                "decisionOfficialJournalPublicationsPublishedDates"  VARCHAR(255),
                "decision_metadataReference"                         VARCHAR(255),
                "decision_language"                                  VARCHAR(50),
                "attachmentLink"                                     TEXT,
                "attachment_language"                                VARCHAR(50),
                "attachment_metadataReference"                       VARCHAR(255),
                "attachmentLanguage"                                 VARCHAR(50),
                "attachmentName"                                     VARCHAR(1000)
            );
            """
        )

    # `commit()` kinnitab andmebaasimuudatused.
    conn.commit()


def load_rows(conn, rows):
    """Laadimine staging kihti: salvesta read tabelisse `staging`.

    Funktsioon saab kaks sisendit:
    - `conn` on andmebaasiühendus;
    - `rows` on loend sõnastikest, mille tagastas `build_rows()`.
    """

    # Kui ridu pole, pole ka midagi laadida.
    if not rows:
        print("- Hoiatus: ridu pole, midagi ei laeta.")
        return

    # Paneme veerunimed jutumärkidesse, sest need on camelCase'is
    # (suur- ja väiketähed segamini). PostgreSQL nõuab sel juhul jutumärke.
    column_list = ", ".join(f'"{column}"' for column in COLUMNS)
    insert_sql = f"INSERT INTO staging ({column_list}) VALUES %s"

    # Teeme igast reast tuppeli väärtustega COLUMNS järjekorras.
    # `value or None` muudab tühja stringi NULL-iks, mis on andmebaasis puhtam.
    values = [
        tuple((row.get(column) or None) for column in COLUMNS)
        for row in rows
    ]

    with conn.cursor() as cur:
        # `TRUNCATE` tühjendab tabeli kiiresti.
        # Nii jääb skript korduvkäivitamisel idempotentseks
        # (mitu käivitust ei tekita dubleeritud ridu).
        cur.execute("TRUNCATE TABLE staging;")

        # `execute_values` lisab kõik read korraga, tükkidena `page_size` kaupa.
        execute_values(cur, insert_sql, values, page_size=1000)

    conn.commit()
    print(f"- Laadisin staging tabelisse {len(values)} rida.")


def main():
    """Käivita kogu töövoog õiges järjekorras.

    `main()` on selle faili põhitöövoog.
    Siin kutsume eelnevad funktsioonid ükshaaval välja ja prindime
    iga etapi järel lühikese vahekokkuvõtte.
    """

    # Siit algab kogu skripti peamine muutujate teekond:
    # get_connection() -> conn
    # fetch_case_data() -> data
    # build_rows(data) -> rows
    conn = get_connection()

    # `try/finally` tähendab: proovi töö ära teha ja sule ühendus igal juhul.
    try:
        print("ETL etapp 1/3: Andmete vastuvõtt")
        data = fetch_case_data()

        print("ETL etapp 2/3: Töötlus")
        rows = build_rows(data)
        # `f"..."` on f-string. See lubab panna muutuja väärtuse otse teksti sisse.
        print(f"- Valmistasin ette {len(rows)} rida (topeltread välistatud).")

        print("ETL etapp 3/3: Laadimine staging kihti")
        create_staging_table(conn)
        load_rows(conn, rows)
        print("Valmis.")
    finally:
        conn.close()


# See plokk käivitab `main()` ainult siis, kui paneme selle faili otse jooksma.
if __name__ == "__main__":
    main()
