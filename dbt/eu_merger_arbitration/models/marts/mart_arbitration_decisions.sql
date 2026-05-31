/*
  Dashboard mart: one row per relevant Art. 6(1)(b) / 8(2) decision.

  Date for period filters: decision_adoption_date (dec_decisionAdoptionDate).
  Hit rule: has_keyword_hit is true when any PDF attachment for the decision
  matched an arbitration keyword.

  Dashboard (Superset / Streamlit) — filter decision_adoption_date to a range, then:
    relevant_decisions = count(*)
    decisions_with_hit = count(*) filter (where has_keyword_hit)
    hit_share          = decisions_with_hit / nullif(relevant_decisions, 0)
*/

select
    case_number || '|' || decision_number as decision_key,
    case_number,
    decision_number,
    min(decision_adoption_date) as decision_adoption_date,

    bool_or(has_keyword_hit) as has_keyword_hit,
    count(*) as attachment_count,
    count(*) filter (where has_keyword_hit) as hit_attachment_count,

    min(decision_type_code) as decision_type_code,
    min(decision_type_label) as decision_type_label,
    min(sector_code) as sector_code,
    min(sector_label) as sector_label,

    min(case_companies) as case_companies,
    min(case_regulation) as case_regulation,
    min(case_simplified_procedure) as case_simplified_procedure

from {{ ref('int_decisions_with_hits') }}
group by case_number, decision_number
