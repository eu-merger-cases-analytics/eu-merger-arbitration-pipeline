with source as (
    select * from {{ source('raw', 'decision_hits') }}
)

select * from source
