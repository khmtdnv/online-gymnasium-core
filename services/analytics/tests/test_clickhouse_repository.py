from datetime import UTC, datetime
from unittest.mock import Mock

import pytest


@pytest.mark.anyio
async def test_repository_inserts_snapshot_batch_in_schema_order() -> None:
    from analytics_service.application.snapshot import LessonSnapshot
    from analytics_service.infrastructure.clickhouse_snapshot_repository import (
        ClickHouseSnapshotRepository,
    )

    client = Mock()
    repository = ClickHouseSnapshotRepository(client)
    first_snapshot = LessonSnapshot(
        event_id=42,
        occurred_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
        lesson_id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 20, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 20, 11, 30, tzinfo=UTC),
        status="planned",
        version=3,
    )
    second_snapshot = LessonSnapshot(
        event_id=43,
        occurred_at=datetime(2026, 9, 19, 10, 1, tzinfo=UTC),
        lesson_id=502,
        class_id=11,
        teacher_id=101,
        subject_id=1001,
        starts_at=datetime(2026, 9, 20, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 20, 12, 45, tzinfo=UTC),
        status="canceled",
        version=4,
    )

    await repository.add_many([first_snapshot, second_snapshot])

    client.insert.assert_called_once_with(
        "lesson_snapshots",
        [
            [
                42,
                datetime(2026, 9, 19, 10, tzinfo=UTC),
                501,
                10,
                100,
                1000,
                datetime(2026, 9, 20, 10, tzinfo=UTC),
                datetime(2026, 9, 20, 11, 30, tzinfo=UTC),
                "planned",
                3,
            ],
            [
                43,
                datetime(2026, 9, 19, 10, 1, tzinfo=UTC),
                502,
                11,
                101,
                1001,
                datetime(2026, 9, 20, 12, tzinfo=UTC),
                datetime(2026, 9, 20, 12, 45, tzinfo=UTC),
                "canceled",
                4,
            ],
        ],
        column_names=[
            "event_id",
            "occurred_at",
            "lesson_id",
            "class_id",
            "teacher_id",
            "subject_id",
            "starts_at",
            "ends_at",
            "status",
            "version",
        ],
    )


@pytest.mark.anyio
async def test_repository_does_not_insert_empty_snapshot_batch() -> None:
    from analytics_service.infrastructure.clickhouse_snapshot_repository import (
        ClickHouseSnapshotRepository,
    )

    client = Mock()
    repository = ClickHouseSnapshotRepository(client)

    await repository.add_many([])

    client.insert.assert_not_called()
