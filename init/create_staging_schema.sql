-- =============================================================================
-- create_staging_schema.sql
-- Creates the raw schema and arbitration_hits table.
-- Run once before loading data with load_hits_to_db.py.
--
-- Usage:
--   docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_staging_schema.sql
-- =============================================================================
 
CREATE SCHEMA IF NOT EXISTS staging;
 
DROP TABLE IF EXISTS staging.arbitration_hits;
 
CREATE TABLE staging.arbitration_hits (
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
 
    -- Matched attachment
    "attachmentMetadataReference"                        VARCHAR(100),
    "attachmentLanguage"                                 VARCHAR(10),
    "attachmentName"                                     TEXT,
    "attachmentLink"                                     TEXT,
 
    -- Match
    "matchKeyword"                                       VARCHAR(100),
    "matchLanguage"                                      VARCHAR(10),
    "matchContext"                                       TEXT,
 
    -- Meta
    "processedAt"                                        VARCHAR(50)
);