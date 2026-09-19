from pathlib import Path

SCHEMA_PATH = Path(__file__).parents[1] / "sql" / "001_schema.sql"


def read_schema() -> str:
    assert SCHEMA_PATH.exists(), "Create sql/001_schema.sql"
    return SCHEMA_PATH.read_text()


def test_schema_defines_append_only_lesson_snapshots() -> None:
    schema = read_schema()

    assert "CREATE TABLE IF NOT EXISTS lesson_snapshots" in schema
    assert "event_id UInt64" in schema
    assert "occurred_at DateTime64(3, 'UTC')" in schema
    assert "lesson_id UInt64" in schema
    assert "class_id UInt64" in schema
    assert "teacher_id UInt64" in schema
    assert "subject_id UInt64" in schema
    assert "starts_at DateTime64(3, 'UTC')" in schema
    assert "ends_at DateTime64(3, 'UTC')" in schema
    assert "status String" in schema
    assert "version UInt64" in schema
    assert "ENGINE = MergeTree" in schema
    assert "ORDER BY (lesson_id, version, event_id)" in schema


def test_schema_defines_current_class_workload_view() -> None:
    schema = read_schema()

    assert "CREATE TABLE IF NOT EXISTS class_daily_workload" in schema
    assert "planned_lessons_count UInt64" in schema
    assert "planned_minutes UInt64" in schema
    assert "refreshed_at DateTime('UTC')" in schema
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS class_daily_workload_mv" in schema
    assert "REFRESH EVERY 1 MINUTE" in schema
    assert "TO class_daily_workload" in schema
    assert "argMax" in schema
    assert "version" in schema
    assert "status = 'planned'" in schema
    assert "dateDiff('minute', starts_at, ends_at)" in schema
