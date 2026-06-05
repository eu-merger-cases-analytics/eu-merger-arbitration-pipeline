/*
  Fails when mart rollup metrics disagree — dashboard hit counts and share would be wrong.

  Rules:
    - every decision has at least one attachment
    - hit attachments cannot exceed total attachments
    - has_keyword_hit matches whether any attachment had a hit
*/

select
    decision_key,
    attachment_count,
    hit_attachment_count,
    has_keyword_hit
from {{ ref('mart_arbitration_decisions') }}
where
    attachment_count < 1
    or hit_attachment_count > attachment_count
    or has_keyword_hit is distinct from (hit_attachment_count > 0)
