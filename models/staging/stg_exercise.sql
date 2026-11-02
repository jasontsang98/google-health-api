{{ config(materialized='view') }}

select *
from read_parquet('{{ var("bronze_exercise_path", "data/bronze/current/exercise.parquet") }}')
