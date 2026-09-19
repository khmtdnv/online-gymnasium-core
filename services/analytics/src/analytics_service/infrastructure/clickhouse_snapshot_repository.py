import asyncio

from clickhouse_connect.driver import Client

from analytics_service.application.snapshot import LessonSnapshot

COLUMN_NAMES = [
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
]


class ClickHouseSnapshotRepository:
    def __init__(self, client: Client) -> None:
        self._client = client

    async def add_many(self, snapshots: list[LessonSnapshot]) -> None:
        if not snapshots:
            return

        rows = [
            [
                snapshot.event_id,
                snapshot.occurred_at,
                snapshot.lesson_id,
                snapshot.class_id,
                snapshot.teacher_id,
                snapshot.subject_id,
                snapshot.starts_at,
                snapshot.ends_at,
                snapshot.status,
                snapshot.version,
            ]
            for snapshot in snapshots
        ]

        await asyncio.to_thread(
            self._client.insert,
            "lesson_snapshots",
            rows,
            column_names=COLUMN_NAMES,
        )
