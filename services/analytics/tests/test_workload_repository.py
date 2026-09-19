from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.anyio
async def test_repository_returns_workload_for_class_and_day() -> None:
    from analytics_service.application.workload import ClassDailyWorkload
    from analytics_service.infrastructure.clickhouse_workload_repository import (
        ClickHouseWorkloadRepository,
    )

    client = Mock()
    refreshed_at = datetime(2026, 9, 19, 8, tzinfo=UTC).replace(tzinfo=None)
    client.query.return_value = SimpleNamespace(
        result_rows=[(10, date(2026, 10, 2), 1, 60, refreshed_at)]
    )
    repository = ClickHouseWorkloadRepository(client)

    workload = await repository.get(class_id=10, day=date(2026, 10, 2))

    assert workload == ClassDailyWorkload(
        class_id=10,
        day=date(2026, 10, 2),
        planned_lessons_count=1,
        planned_minutes=60,
        refreshed_at=datetime(2026, 9, 19, 8, tzinfo=UTC),
    )
    statement = client.query.call_args.args[0]
    assert "FROM class_daily_workload" in statement
    assert "class_id = {class_id:UInt64}" in statement
    assert "day = {day:Date}" in statement
    assert client.query.call_args.kwargs == {
        "parameters": {"class_id": 10, "day": date(2026, 10, 2)}
    }


@pytest.mark.anyio
async def test_repository_returns_none_when_workload_is_missing() -> None:
    from analytics_service.infrastructure.clickhouse_workload_repository import (
        ClickHouseWorkloadRepository,
    )

    client = Mock()
    client.query.return_value = SimpleNamespace(result_rows=[])

    workload = await ClickHouseWorkloadRepository(client).get(
        class_id=10,
        day=date(2026, 10, 2),
    )

    assert workload is None
