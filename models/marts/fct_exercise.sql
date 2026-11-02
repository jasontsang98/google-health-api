{{ config(materialized='table') }}

select
    data_point_id,
    exercise_type,
    display_name,
    try_cast(interval_start_time as timestamptz) at time zone 'Australia/Sydney' as start_time,
    try_cast(interval_end_time as timestamptz) at time zone 'Australia/Sydney' as end_time,
    active_duration_seconds,
    try_cast(created_at_raw as timestamptz) at time zone 'Australia/Sydney' as created_at,
    try_cast(updated_at_raw as timestamptz) at time zone 'Australia/Sydney' as updated_at,
    metrics_summary_json,
    exercise_metadata_json,
    data_source_recording_method,
    data_source_platform
from {{ ref('int_exercise') }}
