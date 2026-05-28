-- =============================================================================
-- create_raw_schema.sql
-- Creates the raw schema and decisions table.
-- Run once before loading data with load_decisions.py.
--
-- Each row = one unique PDF attachment.
-- Primary key is decision_id (auto-increment).
-- attachmentLink is unique and used for upsert logic.
--
-- Usage:
--   docker compose exec db psql -U user -d eu-merger-arbitration \
--     -f /init/create_raw_schema.sql
-- =============================================================================
 
CREATE SCHEMA IF NOT EXISTS raw;
 
DROP TABLE IF EXISTS raw.decisions;
 
CREATE TABLE raw.decisions (
 
    -- Primary key
    "decision_id"                                        SERIAL      PRIMARY KEY,
 
    -- Case level
    "caseNumber"                                         VARCHAR(50),
    "caseTitle"                                          TEXT,
    "caseCompanies"                                      TEXT,
    "caseInstrument"                                     VARCHAR(100),
    "caseRegulation"                                     TEXT,
    "caseSimplified"                                     VARCHAR(100),
    "caseSectors"                                        TEXT,
    "caseInitiationDate"                                 VARCHAR(20),
    "caseNotificationDate"                               VARCHAR(20),
    "caseDeadlineDate"                                   VARCHAR(20),
    "caseLastDecisionDate"                               VARCHAR(20),
    "caseAttachments"                                    TEXT,
 
    -- Decision level
    "decisionNumber"                                     VARCHAR(50),
    "decisionAdoptionDate"                               VARCHAR(20),
    "decisionOfficialJournalPublicationsPublishedDates"  TEXT,
    "decisionTypeCode"                                   VARCHAR(100),
    "decisionTypeLabel"                                  TEXT,
 
    -- Attachment level (one row per unique PDF)
    "attachmentMetadataReference"                        VARCHAR(100),
    "attachmentLanguage"                                 VARCHAR(10),
    "attachmentLanguageLower"                            VARCHAR(10),
    "attachmentName"                                     TEXT,
    "attachmentLink"                                     TEXT        NOT NULL UNIQUE,
 
    -- PDF processing tracking (NULL = not yet processed)
    "pdfProcessedAt"                                     TIMESTAMP,
 
    -- Update tracking
    "isActive"                                           BOOLEAN     NOT NULL DEFAULT TRUE,
    "removedDetectedAt"                                  TIMESTAMP,
    "loadedAt"                                           TIMESTAMP   NOT NULL DEFAULT NOW()
);
 
COMMENT ON TABLE raw.decisions IS
    'One row per unique PDF attachment from EC merger decisions JSON. '
    'attachmentLink is unique and used for upsert logic. '
    'isActive=FALSE means the PDF was present in a previous load but is missing from the current JSON.';