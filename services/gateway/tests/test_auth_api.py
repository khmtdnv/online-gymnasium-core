import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from gateway_service.api.dependencies import get_refresh_handler
from gateway_service.app import create_app
from gateway_service.application.auth import RefreshResult
from gateway_service.application.ports.token_service import (
    DecodedAccess,
    DecodedRefresh,
    IssuedRefresh,
)
from gateway_service.config import GatewaySettings
from gateway_service.domain.user import Role, User
from gateway_service.infrastructure.token_service import PyJwtTokenService


def test_me_reads_bearer_token_and_returns_current_user() -> None:
    user = User(
        id=uuid4(),
        email="student@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=True,
    )
    users = SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    uow = AsyncMock()
    uow.__aenter__.return_value = SimpleNamespace(users=users)
    token_service = Mock()
    token_service.decode_access.return_value = DecodedAccess(
        user_id=user.id, role=Role.STUDENT
    )
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(settings, AsyncMock(), lambda: uow, Mock(), token_service)

    async def request_me():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get(
                "/api/v1/auth/me", headers={"Authorization": "Bearer valid-jwt"}
            )

    response = asyncio.run(request_me())

    assert response.status_code == 200
    assert response.json() == {
        "id": str(user.id),
        "email": "student@example.com",
        "role": "student",
    }
    token_service.decode_access.assert_called_once_with("valid-jwt")


@pytest.mark.parametrize("authorization", [None, "Basic not-a-bearer-token"])
def test_me_rejects_missing_or_non_bearer_authorization(
    authorization: str | None,
) -> None:
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    token_service = Mock()
    app = create_app(settings, AsyncMock(), Mock(), Mock(), token_service)

    async def request_me():
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            headers = {} if authorization is None else {"Authorization": authorization}
            return await client.get("/api/v1/auth/me", headers=headers)

    response = asyncio.run(request_me())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"
    token_service.decode_access.assert_not_called()


def test_refresh_uses_cookie_and_rotates_token_pair() -> None:
    user_id = uuid4()
    old_jti = uuid4()
    new_jti = uuid4()
    user = User(
        id=user_id,
        email="student@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=True,
    )
    users = SimpleNamespace(
        get_by_id=AsyncMock(return_value=user),
        consume_refresh_token=AsyncMock(return_value=True),
        create_refresh_token=AsyncMock(),
    )
    uow = AsyncMock()
    uow.__aenter__.return_value = SimpleNamespace(users=users)
    token_service = Mock()
    token_service.decode_refresh.return_value = DecodedRefresh(
        user_id=user_id, jti=old_jti
    )
    token_service.issue_refresh.return_value = IssuedRefresh(
        token="new-refresh-token",
        jti=new_jti,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    token_service.issue_access.return_value = "new-access-token"
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(
        settings,
        AsyncMock(),
        lambda: uow,
        Mock(),
        token_service,
    )

    async def request_refresh():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            client.cookies.set(
                "refresh_token", "old-refresh-token", path="/api/v1/auth"
            )
            return await client.post("/api/v1/auth/refresh")

    response = asyncio.run(request_refresh())

    assert response.status_code == 200
    assert response.json() == {"access_token": "new-access-token"}
    assert response.cookies.get("refresh_token") == "new-refresh-token"
    set_cookie = response.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=strict" in set_cookie
    assert "path=/api/v1/auth" in set_cookie
    assert "max-age=604800" in set_cookie
    token_service.decode_refresh.assert_called_once_with("old-refresh-token")
    users.consume_refresh_token.assert_awaited_once_with(
        token_id=old_jti, user_id=user_id
    )


def test_refresh_without_cookie_is_rejected_before_handler() -> None:
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(settings, AsyncMock(), Mock(), Mock(), Mock())
    handler = SimpleNamespace(
        handle=AsyncMock(return_value=RefreshResult("access", "refresh"))
    )
    app.dependency_overrides[get_refresh_handler] = lambda: handler

    async def request_refresh():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.post("/api/v1/auth/refresh")

    response = asyncio.run(request_refresh())

    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    handler.handle.assert_not_awaited()


def test_refresh_with_invalid_cookie_returns_401_without_replacement() -> None:
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(settings, AsyncMock(), Mock(), Mock(), PyJwtTokenService(settings))

    async def request_refresh():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.post(
                "/api/v1/auth/refresh",
                headers={"Cookie": "refresh_token=not-a-jwt"},
            )

    response = asyncio.run(request_refresh())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"
    assert "set-cookie" not in response.headers


def test_login_sets_refresh_cookie_and_returns_only_access_token() -> None:
    user = User(
        id=uuid4(),
        email="student@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=True,
    )
    users = SimpleNamespace(
        get_by_email=AsyncMock(return_value=user), create_refresh_token=AsyncMock()
    )
    uow = AsyncMock()
    uow.__aenter__.return_value = SimpleNamespace(users=users)
    password_verifier = Mock()
    password_verifier.verify.return_value = True
    token_service = Mock()
    token_service.issue_access.return_value = "access-token"
    issued = IssuedRefresh(
        token="refresh-token",
        jti=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    token_service.issue_refresh.return_value = issued
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(
        settings, AsyncMock(), lambda: uow, password_verifier, token_service
    )

    async def request_login():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.post(
                "/api/v1/auth/login",
                json={"email": "student@example.com", "password": "secret"},
            )

    response = asyncio.run(request_login())

    assert response.status_code == 200
    assert response.json() == {"access_token": "access-token"}
    assert response.cookies.get("refresh_token") == "refresh-token"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    assert "path=/api/v1/auth" in response.headers["set-cookie"].lower()
    assert response.headers["x-request-id"]
    users.create_refresh_token.assert_awaited_once_with(
        token_id=issued.jti, user_id=user.id, expires_at=issued.expires_at
    )


def test_login_rejects_wrong_password_without_setting_cookie() -> None:
    user = User(
        id=uuid4(),
        email="student@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=True,
    )
    users = SimpleNamespace(
        get_by_email=AsyncMock(return_value=user), create_refresh_token=AsyncMock()
    )
    uow = AsyncMock()
    uow.__aenter__.return_value = SimpleNamespace(users=users)
    password_verifier = Mock()
    password_verifier.verify.return_value = False
    token_service = Mock()
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(
        settings, AsyncMock(), lambda: uow, password_verifier, token_service
    )

    async def request_login():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.post(
                "/api/v1/auth/login",
                json={"email": "student@example.com", "password": "wrong"},
            )

    response = asyncio.run(request_login())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"
    assert "set-cookie" not in response.headers
    users.create_refresh_token.assert_not_awaited()
    token_service.issue_refresh.assert_not_called()


def test_refresh_replay_returns_401_without_issuing_another_token() -> None:
    user = User(
        id=uuid4(),
        email="student@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=True,
    )
    old_jti = uuid4()
    users = SimpleNamespace(
        get_by_id=AsyncMock(return_value=user),
        consume_refresh_token=AsyncMock(side_effect=[True, False]),
        create_refresh_token=AsyncMock(),
    )
    uow = AsyncMock()
    uow.__aenter__.return_value = SimpleNamespace(users=users)
    token_service = Mock()
    token_service.decode_refresh.return_value = DecodedRefresh(user.id, old_jti)
    issued = IssuedRefresh(
        token="new-refresh-token",
        jti=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    token_service.issue_refresh.return_value = issued
    token_service.issue_access.return_value = "new-access-token"
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    app = create_app(settings, AsyncMock(), lambda: uow, Mock(), token_service)

    async def request_twice():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            first = await client.post(
                "/api/v1/auth/refresh",
                headers={"Cookie": "refresh_token=old-refresh-token"},
            )
            replay = await client.post(
                "/api/v1/auth/refresh",
                headers={"Cookie": "refresh_token=old-refresh-token"},
            )
            return first, replay

    first, replay = asyncio.run(request_twice())

    assert first.status_code == 200
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "authentication_error"
    assert "set-cookie" not in replay.headers
    users.create_refresh_token.assert_awaited_once_with(
        token_id=issued.jti, user_id=user.id, expires_at=issued.expires_at
    )
