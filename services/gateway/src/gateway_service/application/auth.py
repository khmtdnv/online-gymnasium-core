from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from gateway_service.application.errors import AuthenticationError
from gateway_service.application.ports.password_service import PasswordService
from gateway_service.application.ports.token_service import TokenService
from gateway_service.application.ports.unit_of_work import UnitOfWork
from gateway_service.domain.user import Role


@dataclass(frozen=True, slots=True)
class RefreshCommand:
    refresh_token: str


@dataclass(frozen=True, slots=True)
class RefreshResult:
    access_token: str
    refresh_token: str


class RefreshHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        token_service: TokenService,
    ) -> None:
        self._uow_factory = uow_factory
        self._token_service = token_service

    async def handle(self, command: RefreshCommand) -> RefreshResult:
        decoded_refresh = self._token_service.decode_refresh(command.refresh_token)

        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id=decoded_refresh.user_id)
            if user is None or not user.is_active:
                raise AuthenticationError

            consumed = await uow.users.consume_refresh_token(
                token_id=decoded_refresh.jti,
                user_id=decoded_refresh.user_id,
            )
            if not consumed:
                raise AuthenticationError

            issued_refresh = self._token_service.issue_refresh(user)
            await uow.users.create_refresh_token(
                token_id=issued_refresh.jti,
                user_id=decoded_refresh.user_id,
                expires_at=issued_refresh.expires_at,
            )

            return RefreshResult(
                access_token=self._token_service.issue_access(user),
                refresh_token=issued_refresh.token,
            )


@dataclass(frozen=True, slots=True)
class LoginCommand:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class LoginResult:
    access_token: str
    refresh_token: str


class LoginHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        password_service: PasswordService,
        token_service: TokenService,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_service = password_service
        self._token_service = token_service

    async def handle(self, command: LoginCommand) -> LoginResult:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_email(command.email)

            if user is None or not user.is_active:
                raise AuthenticationError

            if not self._password_service.verify(command.password, user.password_hash):
                raise AuthenticationError

            access_token = self._token_service.issue_access(user)
            issued_refresh = self._token_service.issue_refresh(user)

            await uow.users.create_refresh_token(
                token_id=issued_refresh.jti,
                user_id=user.id,
                expires_at=issued_refresh.expires_at,
            )

            return LoginResult(
                access_token=access_token,
                refresh_token=issued_refresh.token,
            )


@dataclass(frozen=True, slots=True)
class GetCurrentUserCommand:
    access_token: str


@dataclass(frozen=True, slots=True)
class GetCurrentUserResult:
    id: UUID
    email: str
    role: Role


class GetCurrentUserHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        token_service: TokenService,
    ) -> None:
        self._uow_factory = uow_factory
        self._token_service = token_service

    async def handle(self, command: GetCurrentUserCommand) -> GetCurrentUserResult:
        decoded_access = self._token_service.decode_access(command.access_token)
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(decoded_access.user_id)

            if user is None or not user.is_active:
                raise AuthenticationError

            return GetCurrentUserResult(
                id=user.id,
                email=user.email,
                role=user.role,
            )
