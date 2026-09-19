CREATE TABLE IF NOT EXISTS lesson_snapshots
(
    event_id UInt64,
    occurred_at DateTime64(3, 'UTC'),
    lesson_id UInt64,
    class_id UInt64,
    teacher_id UInt64,
    subject_id UInt64,
    starts_at DateTime64(3, 'UTC'),
    ends_at DateTime64(3, 'UTC'),
    status String,
    version UInt64
)
ENGINE = MergeTree
ORDER BY (lesson_id, version, event_id);


CREATE TABLE IF NOT EXISTS class_daily_workload
(
    class_id UInt64,
    day Date,
    planned_lessons_count UInt64,
    planned_minutes UInt64,
    refreshed_at DateTime('UTC')
)
ENGINE = MergeTree
ORDER BY (class_id, day);


CREATE MATERIALIZED VIEW IF NOT EXISTS class_daily_workload_mv
REFRESH EVERY 1 MINUTE
TO class_daily_workload
AS
WITH latest_lessons AS
(
    SELECT
        lesson_id,
        argMax(class_id, version) AS class_id,
        argMax(starts_at, version) AS starts_at,
        argMax(ends_at, version) AS ends_at,
        argMax(status, version) AS status
    FROM lesson_snapshots
    GROUP BY lesson_id
)
SELECT
    class_id,
    toDate(starts_at) AS day,
    count() AS planned_lessons_count,
    toUInt64(sum(dateDiff('minute', starts_at, ends_at))) AS planned_minutes,
    now('UTC') AS refreshed_at
FROM latest_lessons
WHERE status = 'planned'
GROUP BY class_id, day;