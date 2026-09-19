from datetime import UTC, datetime
from unittest.mock import Mock

import pytest


@pytest.mark.anyio
async def test_repository_inserts_one_snapshot_row_in_schema_order() -> None:
    from analytics_service.application.snapshot import LessonSnapshot
    from analytics_service.infrastructure.clickhouse_snapshot_repository import (
        ClickHouseSnapshotRepository,
    )

    client = Mock()
    repository = ClickHouseSnapshotRepository(client)
    snapshot = LessonSnapshot(
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

    await repository.add(snapshot)

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
            ]
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
