
-- =============================================================================
-- create_raw_schema.sql
-- Creates the raw schema and decisions table.
-- Run once before loading data with load_decisions.py.
--
-- Data columns are added dynamically by load_decisions.py based on
-- the JSON structure. This file only creates the internal tracking columns.
--
-- Re-running drops raw.decision_hits first (FK to decisions), then raw.decisions.
-- After re-run: load_decisions.py, create_raw_decision_hits.sql, load_decision_hits.py.
--
-- Usage:
--   docker compose exec db psql -U user -d eu-merger-arbitration -f /init/create_raw_schema.sql
-- =============================================================================

CREATE SCHEMA IF NOT EXISTS raw;

DROP TABLE IF EXISTS raw.decision_hits;
DROP TABLE IF EXISTS raw.decisions;
 
CREATE TABLE raw.decisions (
 
    -- Primary key
    "decision_id"       SERIAL      PRIMARY KEY,
 
    -- Unique business key — used for upsert and PDF tracking
    "att_attachmentLink"       TEXT        NOT NULL,
    "att_metadataReference"    TEXT        NOT NULL,
    UNIQUE ("att_attachmentLink", "att_metadataReference"),
 
    -- PDF processing tracking (NULL = not yet processed by load_decision_hits.py)
    "pdfProcessedAt"    TIMESTAMP,
    "pdfProcessingError" TEXT,
 
    -- Update tracking
    "isActive"          BOOLEAN     NOT NULL DEFAULT TRUE,
    "removedDetectedAt" TIMESTAMP,
    "loadedAt"          TIMESTAMP   NOT NULL DEFAULT NOW(),
    "lastCheckedAt"     TIMESTAMP
);
 
COMMENT ON TABLE raw.decisions IS
    'One row per unique PDF attachment from EC merger decisions JSON. '
    'Data columns are added dynamically by load_decisions.py. '
    '(att_attachmentLink, att_metadataReference) is the unique business key. '
    'isActive=FALSE means the PDF is missing from the current JSON. '
    'pdfProcessedAt=NULL means the PDF has not been processed by load_decision_hits.py yet. '
    'pdfProcessingError is set when load_decision_hits.py fails on that row.';
 