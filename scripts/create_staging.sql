-- =====================================================================
-- Staging-tabeli loomine EC konkurentsijuhtumite CSV andmete jaoks
-- Veerud vastavad json_to_csv.py väljundi CSV päisele.
-- Kõik veerud on tekstitüüpi (toorandmed algkujul, sh kuupäevad ja
-- JSON-stringid caseSectors / decisionTypes). Tüübiteisendus tehakse
-- hiljem staging-tabelist puhtasse tabelisse laadides.
-- =====================================================================

DROP TABLE IF EXISTS staging;

CREATE TABLE staging (
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
