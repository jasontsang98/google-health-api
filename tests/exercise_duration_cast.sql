-- Every populated API duration must convert cleanly to numeric seconds.
select
    name as data_point_id,
    exercise_activeDuration as active_duration_raw
from {{ ref('stg_exercise') }}
where exercise_activeDuration is not null
  and try_cast(regexp_replace(exercise_activeDuration, 's$', '') as double) is null
