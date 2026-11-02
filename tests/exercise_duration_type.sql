-- The cleansed duration column must be physically stored as DOUBLE.
with model_dependency as (
    select count(*) as row_count
    from {{ ref('int_exercise') }}
), model_columns as (
    select *
    from information_schema.columns
    where table_name = 'int_exercise'
      and column_name = 'active_duration_seconds'
      and data_type <> 'DOUBLE'
)
select model_columns.*
from model_columns
cross join model_dependency
