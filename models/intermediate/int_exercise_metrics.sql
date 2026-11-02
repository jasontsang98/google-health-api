{{ config(materialized='table') }}

with base as (
    select
        data_point_id,
        exercise_type,
        metrics_summary_json
    from {{ ref('int_exercise') }}
), top_level_metrics as (
    select
        base.data_point_id,
        base.exercise_type,
        'summary' as metric_group,
        metrics.key as metric_name_raw,
        metrics.value as metric_value_json
    from base,
        lateral json_each(base.metrics_summary_json) as metrics
    where metrics.key <> 'heartRateZoneDurations'
), heart_rate_zone_metrics as (
    select
        base.data_point_id,
        base.exercise_type,
        'heart_rate_zone_duration' as metric_group,
        metrics.key as metric_name_raw,
        metrics.value as metric_value_json
    from base,
        lateral json_each(base.metrics_summary_json, '$.heartRateZoneDurations') as metrics
), metrics as (
    select * from top_level_metrics
    union all
    select * from heart_rate_zone_metrics
)
select
    data_point_id,
    exercise_type,
    metric_group,
    lower(
        regexp_replace(
            regexp_replace(metric_name_raw, '([a-z0-9])([A-Z])', '\1_\2', 'g'),
            '[^a-zA-Z0-9]+',
            '_',
            'g'
        )
    ) as metric_name,
    case
        when right(json_extract_string(metric_value_json, '$'), 1) = 's'
            then try_cast(regexp_replace(json_extract_string(metric_value_json, '$'), 's$', '') as double)
        else try_cast(json_extract_string(metric_value_json, '$') as double)
    end as metric_value,
    case
        when right(json_extract_string(metric_value_json, '$'), 1) = 's' then 'seconds'
        else null
    end as metric_unit,
    json_extract_string(metric_value_json, '$') as metric_value_raw
from metrics
