/*
  Relevant attachments left-joined to keyword hits.
  One row per relevant attachment; hit columns are null when no keyword match.
*/

select
    d.*,
    h.hit_id,
    h."matchedKeywords" as matched_keywords,
    h."matchedLanguage" as matched_language,
    h."matchContext" as match_context,
    h."loadedAt" as hit_loaded_at,
    (h.decision_id is not null) as has_keyword_hit

from {{ ref('int_relevant_decisions') }} as d
left join {{ ref('stg_decision_hits') }} as h
    on d.decision_id = h.decision_id
