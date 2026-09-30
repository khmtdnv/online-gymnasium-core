import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from httpx import ASGITransport, AsyncClient

from gateway_service.app import create_app
from gateway_service.config import GatewaySettings


def make_app():
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    return create_app(settings, AsyncMock(), Mock(), Mock(), Mock())


def request(app, path: str, *, json: object = None):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            return await client.post(path, json=json)

    return asyncio.run(send())


def assert_error_envelope(response, *, status_code: int, code: str) -> None:
    assert response.status_code == status_code
    error = response.json()["error"]
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert UUID(error["request_id"])
    assert response.headers["x-request-id"] == error["request_id"]


def test_authentication_error_uses_gateway_error_envelope() -> None:
    response = request(make_app(), "/api/v1/auth/refresh")

    assert_error_envelope(response, status_code=401, code="authentication_error")


def test_request_validation_error_uses_gateway_error_envelope() -> None:
    response = request(make_app(), "/api/v1/auth/login", json={"email": "x@y.z"})

    assert_error_envelope(response, status_code=422, code="validation_error")


def test_missing_route_uses_gateway_error_envelope() -> None:
    response = request(make_app(), "/no-such-route")

    assert_error_envelope(response, status_code=404, code="not_found")


def test_unexpected_exception_is_sanitized_and_traceable() -> None:
    app = make_app()

    @app.post("/explode")
    async def explode():
        raise RuntimeError("secret internal details")

    response = request(app, "/explode")

    assert_error_envelope(response, status_code=500, code="internal_error")
    assert "secret internal details" not in response.text
