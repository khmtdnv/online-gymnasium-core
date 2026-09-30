import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Self
from uuid import UUID, uuid4

import pytest

from gateway_service.domain.user import Role, User


class FakeUserRepository:
    def __init__(self, user: User, *, can_consume: bool = True) -> None:
        self.user = user
        self.can_consume = can_consume
        self.fail_create = False
        self.uow: FakeUnitOfWork | None = None
        self.calls: list[tuple[object, ...]] = []

    def _assert_inside_uow(self) -> None:
        assert self.uow is not None and self.uow.active

    async def get_by_id(self, user_id: UUID) -> User | None:
        self._assert_inside_uow()
        self.calls.append(("get_by_id", user_id))
        return self.user if self.user.id == user_id else None

    async def get_by_email(self, email: str) -> User | None:
        self._assert_inside_uow()
        self.calls.append(("get_by_email", email))
        return self.user if self.user.email == email else None

    async def consume_refresh_token(self, token_id: UUID, user_id: UUID) -> bool:
        self._assert_inside_uow()
        self.calls.append(("consume_refresh_token", token_id, user_id))
        return self.can_consume

    async def create_refresh_token(
        self, token_id: UUID, user_id: UUID, expires_at: datetime
    ) -> None:
        self._assert_inside_uow()
        self.calls.append(("create_refresh_token", token_id, user_id, expires_at))
        if self.fail_create:
            raise RuntimeError("new refresh token insert failed")


class FakeUnitOfWork:
    def __init__(self, users: FakeUserRepository) -> None:
        self.users = users
        self.users.uow = self
        self.active = False
        self.entries = 0
        self.fail_commit = False
        self.exit_errors: list[type[BaseException] | None] = []

    async def __aenter__(self) -> Self:
        self.active = True
        self.entries += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        self.exit_errors.append(exc_type)
        self.active = False
        if exc_type is None and self.fail_commit:
            raise RuntimeError("commit failed")


class FakePasswordVerifier:
    def __init__(self, *, matches: bool = True) -> None:
        self.matches = matches
        self.calls: list[tuple[str, str]] = []

    def verify(self, plain_password: str, password_hash: str) -> bool:
        self.calls.append((plain_password, password_hash))
        return self.matches


class FakeTokenService:
    def __init__(
        self, *, user_id: UUID, old_jti: UUID, new_jti: UUID, expires_at: datetime
    ) -> None:
        self.user_id = user_id
        self.old_jti = old_jti
        self.new_jti = new_jti
        self.expires_at = expires_at
        self.access_role = Role.STUDENT
        self.access_issued = False
        self.refresh_issued = False

    def decode_refresh(self, token: str) -> SimpleNamespace:
        assert token == "old-refresh-token"
        return SimpleNamespace(user_id=self.user_id, jti=self.old_jti)

    def decode_access(self, token: str) -> SimpleNamespace:
        from gateway_service.application.errors import AuthenticationError

        if token != "valid-access-token":
            raise AuthenticationError
        return SimpleNamespace(user_id=self.user_id, role=self.access_role)

    def issue_access(self, user: User) -> str:
        assert user.id == self.user_id
        self.access_issued = True
        return "new-access-token"

    def issue_refresh(self, user: User) -> SimpleNamespace:
        assert user.id == self.user_id
        self.refresh_issued = True
        return SimpleNamespace(
            token="new-refresh-token", jti=self.new_jti, expires_at=self.expires_at
        )


def make_fakes(
    *, can_consume: bool = True, active: bool = True
) -> tuple[FakeUnitOfWork, FakeTokenService]:
    user_id = uuid4()
    user = User(
        id=user_id,
        email="student@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=active,
    )
    users = FakeUserRepository(user, can_consume=can_consume)
    uow = FakeUnitOfWork(users)
    tokens = FakeTokenService(
        user_id=user_id,
        old_jti=uuid4(),
        new_jti=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    return uow, tokens


def test_refresh_consumes_old_token_and_stores_new_token_in_one_uow() -> None:
    from gateway_service.application.auth import RefreshCommand, RefreshHandler

    uow, tokens = make_fakes()
    handler = RefreshHandler(uow_factory=lambda: uow, token_service=tokens)

    result = asyncio.run(
        handler.handle(RefreshCommand(refresh_token="old-refresh-token"))
    )

    assert result.access_token == "new-access-token"
    assert result.refresh_token == "new-refresh-token"
    assert uow.entries == 1
    assert uow.exit_errors == [None]
    assert uow.users.calls == [
        ("get_by_id", tokens.user_id),
        ("consume_refresh_token", tokens.old_jti, tokens.user_id),
        (
            "create_refresh_token",
            tokens.new_jti,
            tokens.user_id,
            tokens.expires_at,
        ),
    ]


def test_refresh_rejects_replay_without_creating_another_token() -> None:
    from gateway_service.application.auth import RefreshCommand, RefreshHandler
    from gateway_service.application.errors import AuthenticationError

    uow, tokens = make_fakes(can_consume=False)
    handler = RefreshHandler(uow_factory=lambda: uow, token_service=tokens)

    with pytest.raises(AuthenticationError):
        asyncio.run(handler.handle(RefreshCommand(refresh_token="old-refresh-token")))

    assert uow.entries == 1
    assert uow.exit_errors == [AuthenticationError]
    assert all(call[0] != "create_refresh_token" for call in uow.users.calls)
    assert not tokens.access_issued
    assert not tokens.refresh_issued


def test_refresh_does_not_consume_token_for_inactive_user() -> None:
    from gateway_service.application.auth import RefreshCommand, RefreshHandler
    from gateway_service.application.errors import AuthenticationError

    uow, tokens = make_fakes(active=False)
    handler = RefreshHandler(uow_factory=lambda: uow, token_service=tokens)

    with pytest.raises(AuthenticationError):
        asyncio.run(handler.handle(RefreshCommand(refresh_token="old-refresh-token")))

    assert uow.entries == 1
    assert uow.exit_errors == [AuthenticationError]
    assert all(call[0] != "consume_refresh_token" for call in uow.users.calls)
    assert all(call[0] != "create_refresh_token" for call in uow.users.calls)


def test_refresh_insert_failure_leaves_same_uow_with_error() -> None:
    from gateway_service.application.auth import RefreshCommand, RefreshHandler

    uow, tokens = make_fakes()
    uow.users.fail_create = True
    handler = RefreshHandler(uow_factory=lambda: uow, token_service=tokens)

    with pytest.raises(RuntimeError, match="new refresh token insert failed"):
        asyncio.run(handler.handle(RefreshCommand(refresh_token="old-refresh-token")))

    assert uow.entries == 1
    assert uow.exit_errors == [RuntimeError]
    assert ("consume_refresh_token", tokens.old_jti, tokens.user_id) in uow.users.calls
    assert (
        "create_refresh_token",
        tokens.new_jti,
        tokens.user_id,
        tokens.expires_at,
    ) in uow.users.calls


def test_login_verifies_password_and_persists_refresh_id_in_one_uow() -> None:
    from gateway_service.application.auth import LoginCommand, LoginHandler

    uow, tokens = make_fakes()
    passwords = FakePasswordVerifier()
    handler = LoginHandler(lambda: uow, passwords, tokens)

    result = asyncio.run(
        handler.handle(LoginCommand(email="student@example.com", password="secret"))
    )

    assert result.access_token == "new-access-token"
    assert result.refresh_token == "new-refresh-token"
    assert passwords.calls == [("secret", "stored-hash")]
    assert uow.entries == 1
    assert uow.exit_errors == [None]
    assert uow.users.calls == [
        ("get_by_email", "student@example.com"),
        ("create_refresh_token", tokens.new_jti, tokens.user_id, tokens.expires_at),
    ]


def test_login_rejects_wrong_password_without_issuing_tokens() -> None:
    from gateway_service.application.auth import LoginCommand, LoginHandler
    from gateway_service.application.errors import AuthenticationError

    uow, tokens = make_fakes()
    passwords = FakePasswordVerifier(matches=False)
    handler = LoginHandler(lambda: uow, passwords, tokens)

    with pytest.raises(AuthenticationError):
        asyncio.run(
            handler.handle(LoginCommand(email="student@example.com", password="wrong"))
        )

    assert passwords.calls == [("wrong", "stored-hash")]
    assert uow.exit_errors == [AuthenticationError]
    assert uow.users.calls == [("get_by_email", "student@example.com")]
    assert not tokens.access_issued
    assert not tokens.refresh_issued


@pytest.mark.parametrize(
    ("email", "active"),
    [("missing@example.com", True), ("student@example.com", False)],
)
def test_login_rejects_missing_or_inactive_user(email: str, active: bool) -> None:
    from gateway_service.application.auth import LoginCommand, LoginHandler
    from gateway_service.application.errors import AuthenticationError

    uow, tokens = make_fakes(active=active)
    passwords = FakePasswordVerifier()
    handler = LoginHandler(lambda: uow, passwords, tokens)

    with pytest.raises(AuthenticationError):
        asyncio.run(handler.handle(LoginCommand(email=email, password="secret")))

    assert passwords.calls == []
    assert uow.exit_errors == [AuthenticationError]
    assert uow.users.calls == [("get_by_email", email)]
    assert not tokens.access_issued
    assert not tokens.refresh_issued


def test_login_insert_failure_does_not_return_tokens() -> None:
    from gateway_service.application.auth import LoginCommand, LoginHandler

    uow, tokens = make_fakes()
    uow.users.fail_create = True
    handler = LoginHandler(lambda: uow, FakePasswordVerifier(), tokens)

    with pytest.raises(RuntimeError, match="new refresh token insert failed"):
        asyncio.run(
            handler.handle(LoginCommand(email="student@example.com", password="secret"))
        )

    assert uow.entries == 1
    assert uow.exit_errors == [RuntimeError]


def test_login_commit_failure_does_not_return_tokens() -> None:
    from gateway_service.application.auth import LoginCommand, LoginHandler

    uow, tokens = make_fakes()
    uow.fail_commit = True
    handler = LoginHandler(lambda: uow, FakePasswordVerifier(), tokens)

    with pytest.raises(RuntimeError, match="commit failed"):
        asyncio.run(
            handler.handle(LoginCommand(email="student@example.com", password="secret"))
        )

    assert uow.entries == 1
    assert uow.exit_errors == [None]
    assert (
        "create_refresh_token",
        tokens.new_jti,
        tokens.user_id,
        tokens.expires_at,
    ) in uow.users.calls


def test_get_current_user_returns_safe_current_database_identity() -> None:
    from gateway_service.application.auth import (
        GetCurrentUserCommand,
        GetCurrentUserHandler,
    )

    uow, tokens = make_fakes()
    handler = GetCurrentUserHandler(lambda: uow, tokens)

    result = asyncio.run(
        handler.handle(GetCurrentUserCommand(access_token="valid-access-token"))
    )

    assert result.id == tokens.user_id
    assert result.email == "student@example.com"
    assert result.role is Role.STUDENT
    assert not hasattr(result, "password_hash")
    assert uow.entries == 1
    assert uow.users.calls == [("get_by_id", tokens.user_id)]


def test_get_current_user_returns_current_role_when_token_role_is_stale() -> None:
    from gateway_service.application.auth import (
        GetCurrentUserCommand,
        GetCurrentUserHandler,
    )

    uow, tokens = make_fakes()
    tokens.access_role = Role.TEACHER
    handler = GetCurrentUserHandler(lambda: uow, tokens)

    result = asyncio.run(
        handler.handle(GetCurrentUserCommand(access_token="valid-access-token"))
    )

    assert result.id == tokens.user_id
    assert result.role is Role.STUDENT
    assert uow.entries == 1
    assert uow.exit_errors == [None]
    assert uow.users.calls == [("get_by_id", tokens.user_id)]


@pytest.mark.parametrize("active", [True, False])
def test_get_current_user_rejects_missing_or_inactive_user(active: bool) -> None:
    from gateway_service.application.auth import (
        GetCurrentUserCommand,
        GetCurrentUserHandler,
    )
    from gateway_service.application.errors import AuthenticationError

    uow, tokens = make_fakes(active=active)
    if active:
        tokens.user_id = uuid4()
    handler = GetCurrentUserHandler(lambda: uow, tokens)

    with pytest.raises(AuthenticationError):
        asyncio.run(
            handler.handle(GetCurrentUserCommand(access_token="valid-access-token"))
        )

    assert uow.entries == 1
    assert uow.exit_errors == [AuthenticationError]
    assert uow.users.calls == [("get_by_id", tokens.user_id)]


def test_get_current_user_rejects_invalid_access_token_before_opening_uow() -> None:
    from gateway_service.application.auth import (
        GetCurrentUserCommand,
        GetCurrentUserHandler,
    )
    from gateway_service.application.errors import AuthenticationError

    uow, tokens = make_fakes()
    handler = GetCurrentUserHandler(lambda: uow, tokens)

    with pytest.raises(AuthenticationError):
        asyncio.run(handler.handle(GetCurrentUserCommand(access_token="invalid-token")))

    assert uow.entries == 0
    assert uow.users.calls == []
