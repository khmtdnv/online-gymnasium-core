from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

from gateway_service.application.errors import (
    InvalidParentStudentRolesError,
    UserNotFoundError,
)
from gateway_service.application.ports.password_service import PasswordService
from gateway_service.application.ports.unit_of_work import UnitOfWork
from gateway_service.domain.user import Role, User


@dataclass(frozen=True, slots=True)
class CreateUserCommand:
    email: str
    password: str
    role: Role


@dataclass(frozen=True, slots=True)
class UserSummary:
    id: UUID
    email: str
    role: Role
    is_active: bool


class CreateUserHandler:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        password_service: PasswordService,
    ) -> None:
        self._uow_factory = uow_factory
        self._password_service = password_service

    async def handle(self, command: CreateUserCommand) -> UserSummary:
        password_hash = self._password_service.hash(command.password)
        user = User(
            id=uuid4(),
            email=command.email,
            role=command.role,
            password_hash=password_hash,
            is_active=True,
        )
        async with self._uow_factory() as uow:
            await uow.users.create_user(user)

        return UserSummary(
            id=user.id,
            email=user.email,
            role=user.role,
            is_active=user.is_active,
        )


class ListUsersHandler:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def handle(self) -> list[UserSummary]:
        async with self._uow_factory() as uow:
            users = await uow.users.list_users()

        users_list = []
        for user in users:
            users_list.append(
                UserSummary(
                    id=user.id,
                    email=user.email,
                    role=user.role,
                    is_active=user.is_active,
                )
            )

        return users_list


@dataclass(frozen=True, slots=True)
class LinkParentStudentCommand:
    parent_id: UUID
    student_id: UUID


class LinkParentStudentHandler:
    def __init__(self, uow_factory: Callable[[], UnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def handle(self, command: LinkParentStudentCommand) -> bool:
        async with self._uow_factory() as uow:
            parent = await uow.users.get_by_id(command.parent_id)
            student = await uow.users.get_by_id(command.student_id)

            if parent is None or student is None:
                raise UserNotFoundError

            if parent.role is not Role.PARENT or student.role is not Role.STUDENT:
                raise InvalidParentStudentRolesError

            return await uow.users.create_parent_student_link(
                parent_id=parent.id,
                student_id=student.id,
            )
