import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import SQLAlchemyError

from gateway_service.app import create_app
from gateway_service.config import GatewaySettings


def make_app(engine: MagicMock):
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    return create_app(settings, engine, Mock(), Mock(), Mock())


def request(app, path: str):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    return asyncio.run(send())


def test_live_is_ok_without_contacting_database() -> None:
    engine = MagicMock()

    response = request(make_app(engine), "/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    engine.connect.assert_not_called()


def test_ready_is_ok_when_database_accepts_probe() -> None:
    engine = MagicMock()
    connection = AsyncMock()
    engine.connect.return_value.__aenter__.return_value = connection

    response = request(make_app(engine), "/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    connection.execute.assert_awaited_once()
    assert str(connection.execute.await_args.args[0]) == "SELECT 1"


@pytest.mark.parametrize(
    "failure", [OSError("connection refused"), SQLAlchemyError("db error")]
)
def test_ready_reports_unavailable_without_leaking_database_error(
    failure: Exception,
) -> None:
    engine = MagicMock()
    engine.connect.return_value.__aenter__.side_effect = failure

    response = request(make_app(engine), "/health/ready")

    assert response.status_code == 503
    assert "connection refused" not in response.text
    assert "db error" not in response.text
    error = response.json()["error"]
    assert UUID(error["request_id"])
    assert response.headers["x-request-id"] == error["request_id"]
