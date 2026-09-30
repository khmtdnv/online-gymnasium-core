import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from gateway_service.app import create_app
from gateway_service.config import GatewaySettings
from gateway_service.domain.user import Role, User


def make_app(users: object):
    settings = GatewaySettings(
        database_url="postgresql+asyncpg://gateway:password@localhost/gateway",
        jwt_secret="test-signing-secret-for-hs256-32-bytes",
        backoffice_service_token="test-backoffice-token",
        _env_file=None,
    )
    uow = AsyncMock()
    uow.__aenter__.return_value = SimpleNamespace(users=users)
    uow.__aexit__.return_value = False
    uow_factory = Mock(return_value=uow)
    password_service = Mock()
    password_service.hash.return_value = "encoded-password-hash"
    app = create_app(settings, AsyncMock(), uow_factory, password_service, Mock())
    return app, uow_factory


def request(
    app,
    method: str,
    *,
    path: str = "/internal/backoffice/users",
    headers: dict[str, str] | None = None,
    json=None,
):
    async def send():
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, headers=headers, json=json)

    return asyncio.run(send())


@pytest.mark.parametrize(
    "headers",
    [
        None,
        {"X-Backoffice-Service-Token": ""},
        {"X-Backoffice-Service-Token": "wrong-token"},
    ],
)
def test_list_users_rejects_missing_empty_or_wrong_service_token(
    headers: dict[str, str] | None,
) -> None:
    users = SimpleNamespace(list_users=AsyncMock(return_value=[]))
    app, uow_factory = make_app(users)

    response = request(app, "GET", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
    uow_factory.assert_not_called()


def test_list_users_returns_safe_user_fields() -> None:
    user_id = uuid4()
    users = SimpleNamespace(
        list_users=AsyncMock(
            return_value=[
                User(
                    id=user_id,
                    email="student@example.com",
                    role=Role.STUDENT,
                    password_hash="never-send-this",
                    is_active=True,
                )
            ]
        )
    )
    app, _ = make_app(users)

    response = request(
        app, "GET", headers={"X-Backoffice-Service-Token": "test-backoffice-token"}
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(user_id),
            "email": "student@example.com",
            "role": "student",
            "is_active": True,
        }
    ]


def test_list_users_returns_empty_list_when_no_users_exist() -> None:
    users = SimpleNamespace(list_users=AsyncMock(return_value=[]))
    app, _ = make_app(users)

    response = request(
        app, "GET", headers={"X-Backoffice-Service-Token": "test-backoffice-token"}
    )

    assert response.status_code == 200
    assert response.json() == []


def test_backoffice_routes_are_absent_from_public_openapi() -> None:
    app, _ = make_app(SimpleNamespace())

    assert "/internal/backoffice/users" not in app.openapi()["paths"]


def test_create_user_returns_conflict_for_existing_email() -> None:
    from gateway_service.application.errors import EmailAlreadyExistsError

    users = SimpleNamespace(
        create_user=AsyncMock(side_effect=EmailAlreadyExistsError())
    )
    app, _ = make_app(users)

    response = request(
        app,
        "POST",
        headers={"X-Backoffice-Service-Token": "test-backoffice-token"},
        json={
            "email": "teacher@example.com",
            "password": "strong-password",
            "role": "teacher",
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "strong-password" not in response.text


def test_link_parent_student_returns_created_for_new_pair() -> None:
    parent_id, student_id = uuid4(), uuid4()
    users = SimpleNamespace(
        get_by_id=AsyncMock(
            side_effect=[
                User(parent_id, "parent@example.com", Role.PARENT, "hash", True),
                User(student_id, "student@example.com", Role.STUDENT, "hash", True),
            ]
        ),
        create_parent_student_link=AsyncMock(return_value=True),
    )
    app, _ = make_app(users)

    response = request(
        app,
        "PUT",
        path=f"/internal/backoffice/parents/{parent_id}/children/{student_id}",
        headers={"X-Backoffice-Service-Token": "test-backoffice-token"},
    )

    assert response.status_code == 201
    assert response.content == b""
    users.create_parent_student_link.assert_awaited_once_with(
        parent_id=parent_id, student_id=student_id
    )


@pytest.mark.parametrize(
    ("user_roles", "expected_status", "expected_code"),
    [
        ((None, None), 404, "not_found"),
        ((Role.TEACHER, Role.STUDENT), 422, "validation_error"),
        ((Role.PARENT, Role.TEACHER), 422, "validation_error"),
    ],
)
def test_link_parent_student_rejects_missing_user_or_wrong_roles(
    user_roles: tuple[Role | None, Role | None],
    expected_status: int,
    expected_code: str,
) -> None:
    parent_id, student_id = uuid4(), uuid4()
    users = SimpleNamespace(
        get_by_id=AsyncMock(
            side_effect=[
                None
                if user_roles[0] is None
                else User(parent_id, "parent@example.com", user_roles[0], "hash", True),
                None
                if user_roles[1] is None
                else User(
                    student_id, "student@example.com", user_roles[1], "hash", True
                ),
            ]
        ),
        create_parent_student_link=AsyncMock(),
    )
    app, _ = make_app(users)

    response = request(
        app,
        "PUT",
        path=f"/internal/backoffice/parents/{parent_id}/children/{student_id}",
        headers={"X-Backoffice-Service-Token": "test-backoffice-token"},
    )

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code
    users.create_parent_student_link.assert_not_awaited()


def test_link_parent_student_returns_no_content_for_existing_pair() -> None:
    parent_id, student_id = uuid4(), uuid4()
    users = SimpleNamespace(
        get_by_id=AsyncMock(
            side_effect=[
                User(parent_id, "parent@example.com", Role.PARENT, "hash", True),
                User(student_id, "student@example.com", Role.STUDENT, "hash", True),
            ]
        ),
        create_parent_student_link=AsyncMock(return_value=False),
    )
    app, _ = make_app(users)

    response = request(
        app,
        "PUT",
        path=f"/internal/backoffice/parents/{parent_id}/children/{student_id}",
        headers={"X-Backoffice-Service-Token": "test-backoffice-token"},
    )

    assert response.status_code == 204
    assert response.content == b""
