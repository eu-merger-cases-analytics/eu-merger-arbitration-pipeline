
-- =============================================================================
-- create_raw_decision_hits.sql
-- Creates the raw.decision_hits table for keyword matches found in PDFs.
-- Run after create_raw_schema.sql and load_decisions.py.
--
-- Case, decision, and attachment metadata columns are added dynamically by
-- load_decision_hits.py when copying from raw.decisions (all as TEXT).
-- This file only creates the key, hit, and tracking columns.
--
-- Usage:
--   docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_decision_hits.sql
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw;

DROP TABLE IF EXISTS raw.decision_hits;

CREATE TABLE raw.decision_hits (

    -- Primary key
    "hit_id"                SERIAL      PRIMARY KEY,

    -- Link to source row in raw.decisions (one hit row per processed attachment)
    "decision_id"           INTEGER     NOT NULL
        REFERENCES raw.decisions ("decision_id") ON DELETE CASCADE,

    -- Same business key as raw.decisions (for upsert and traceability)
    "att_attachmentLink"       TEXT        NOT NULL,
    "att_metadataReference"    TEXT        NOT NULL,
    UNIQUE ("att_attachmentLink", "att_metadataReference"),
    UNIQUE ("decision_id"),

    -- Keyword match details (set by load_decision_hits.py)
    "matchedKeywords"       TEXT        NOT NULL,
    "matchedLanguage"       TEXT        NOT NULL,
    "matchContext"          TEXT,

    -- Load tracking
    "loadedAt"              TIMESTAMP   NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE raw.decision_hits IS
    'One row per PDF attachment where arbitration keywords were found. '
    'Metadata columns (case_*, dec_*, att_*, etc.) are added dynamically by load_decision_hits.py. '
    'decision_id references raw.decisions; (att_attachmentLink, att_metadataReference) matches that table. '
    'Attachments with a keyword hit are stored here; Art. 6(1)(b) / 8(2) filtering is done in dbt.';

COMMENT ON COLUMN raw.decision_hits."matchedKeywords" IS
    'Matched keyword pattern(s) from config/keywords.txt (pipe-separated if multiple).';

COMMENT ON COLUMN raw.decision_hits."matchedLanguage" IS
    'Language code used for matching (from attachment metadata).';

COMMENT ON COLUMN raw.decision_hits."matchContext" IS
    'Text snippet around the match (~100 characters).';
