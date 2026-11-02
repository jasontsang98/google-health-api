{{ config(materialized='table') }}

select
    data_point_id,
    max(case when metric_group = 'summary' and metric_name = 'calories_kcal' then metric_value end) as calories_kcal,
    max(case when metric_group = 'summary' and metric_name = 'distance_millimeters' then metric_value end) as distance_millimeters,
    max(case when metric_group = 'summary' and metric_name = 'steps' then metric_value end) as steps,
    max(case when metric_group = 'summary' and metric_name = 'average_heart_rate_beats_per_minute' then metric_value end) as average_heart_rate_beats_per_minute,
    max(case when metric_group = 'summary' and metric_name = 'active_zone_minutes' then metric_value end) as active_zone_minutes,
    max(case when metric_group = 'heart_rate_zone_duration' and metric_name = 'light_time' then metric_value end) as light_zone_seconds,
    max(case when metric_group = 'heart_rate_zone_duration' and metric_name = 'moderate_time' then metric_value end) as moderate_zone_seconds,
    max(case when metric_group = 'heart_rate_zone_duration' and metric_name = 'vigorous_time' then metric_value end) as vigorous_zone_seconds,
    max(case when metric_group = 'heart_rate_zone_duration' and metric_name = 'peak_time' then metric_value end) as peak_zone_seconds
from {{ ref('int_exercise_metrics') }}
where exercise_type = 'BADMINTON'
group by data_point_id
