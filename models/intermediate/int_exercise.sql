{{ config(materialized='table') }}

select
    regexp_extract(name, '([^/]+)$', 1) as data_point_id,
    data_source_recording_method,
    data_source_platform,
    interval_start_time,
    interval_end_time,
    exercise_exerciseType as exercise_type,
    exercise_displayName as display_name,
    try_cast(regexp_replace(exercise_activeDuration, 's$', '') as double) as active_duration_seconds,
    exercise_createTime as created_at_raw,
    exercise_updateTime as updated_at_raw,
    exercise_metricsSummary as metrics_summary_json,
    exercise_exerciseMetadata as exercise_metadata_json
from {{ ref('stg_exercise') }}
where upper(data_source_platform) = 'FITBIT'
