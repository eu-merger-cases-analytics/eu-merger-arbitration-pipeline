/*
  Art. 6(1)(b) and Art. 8(2) attachments from staging, with JSON metadata
  parsed into flat columns for analysis.
*/

with decisions as (

    select * from {{ ref('stg_decisions') }}

),

filtered as (

    select *
    from decisions
    where
        "isActive" = true
        and (
            "dec_decisionTypes" like '%6(1)(b)%'
            or "dec_decisionTypes" like '%8(2)%'
        )

)

select
    decision_id,
    "case_caseNumber" as case_number,
    "dec_decisionNumber" as decision_number,
    "att_attachmentLink" as attachment_link,
    "att_metadataReference" as metadata_reference,
    "att_attachmentLanguage" as attachment_language,

    -- Decision type (JSON-like text from source; regex avoids invalid JSON rows)
    "dec_decisionTypes" as decision_types_raw,
    nullif(substring("dec_decisionTypes" from '"code"\s*:\s*"([^"]+)"'), '')
        as decision_type_code,
    nullif(substring("dec_decisionTypes" from '"label"\s*:\s*"([^"]+)"'), '')
        as decision_type_label,

    -- NACE sector (same pattern; some rows contain non-JSON multi-value text)
    "case_caseSectors" as sectors_raw,
    nullif(substring("case_caseSectors" from '"code"\s*:\s*"([^"]+)"'), '')
        as sector_code,
    nullif(substring("case_caseSectors" from '"label"\s*:\s*"([^"]+)"'), '')
        as sector_label,

    -- Dates
    nullif(btrim("dec_decisionAdoptionDate"), '')::date as decision_adoption_date,
    nullif(btrim("case_caseNotificationDate"), '')::date as case_notification_date,

    -- PDF processing status (denominator quality / completeness)
    "pdfProcessedAt" as pdf_processed_at,
    "pdfProcessingError" as pdf_processing_error,
    ("pdfProcessedAt" is not null) as is_pdf_processed,
    ("pdfProcessingError" is null and "pdfProcessedAt" is not null) as is_pdf_ok,

    "case_caseCompanies" as case_companies,
    "case_caseRegulation" as case_regulation,
    "case_caseSimplified" as case_simplified_procedure

from filtered
