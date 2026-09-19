import clickhouse_connect

from analytics_service.api.app import create_app
from analytics_service.config import AnalyticsApiSettings
from analytics_service.infrastructure.clickhouse_workload_repository import (
    ClickHouseWorkloadRepository,
)

settings = AnalyticsApiSettings()
client = clickhouse_connect.get_client(
    host=settings.clickhouse_host,
    port=settings.clickhouse_port,
    username=settings.clickhouse_user,
    password=settings.clickhouse_password,
)
app = create_app(
    repository_factory=lambda: ClickHouseWorkloadRepository(client),
)
