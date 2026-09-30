import asyncio
from typing import Self
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from gateway_service.domain.user import Role, User


class FakeUserRepository:
    def __init__(self) -> None:
        self.created: list[User] = []

    async def get_by_email(self, email: str) -> User | None:
        return None

    async def create_user(self, user: User) -> None:
        self.created.append(user)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.users = FakeUserRepository()
        self.exited = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        self.exited = True


class FakePasswordService:
    def __init__(self) -> None:
        self.received_passwords: list[str] = []

    def hash(self, password: str) -> str:
        self.received_passwords.append(password)
        return "encoded-password-hash"


def test_create_user_stores_hash_instead_of_plaintext_password() -> None:
    from gateway_service.application.backoffice import (
        CreateUserCommand,
        CreateUserHandler,
    )

    uow = FakeUnitOfWork()
    password_service = FakePasswordService()
    handler = CreateUserHandler(
        uow_factory=lambda: uow, password_service=password_service
    )

    result = asyncio.run(
        handler.handle(
            CreateUserCommand(
                email="teacher@example.com",
                password="strong-password",
                role=Role.TEACHER,
            )
        )
    )

    assert len(uow.users.created) == 1
    stored_user = uow.users.created[0]
    assert isinstance(stored_user.id, UUID)
    assert stored_user.email == "teacher@example.com"
    assert stored_user.role is Role.TEACHER
    assert stored_user.password_hash == "encoded-password-hash"
    assert stored_user.is_active
    assert password_service.received_passwords == ["strong-password"]
    assert result.id == stored_user.id
    assert uow.exited


def test_link_parent_student_accepts_correct_roles() -> None:
    from gateway_service.application.backoffice import (
        LinkParentStudentCommand,
        LinkParentStudentHandler,
    )

    parent_id, student_id = uuid4(), uuid4()
    users = AsyncMock()
    users.create_parent_student_link.return_value = True
    users.get_by_id.side_effect = [
        User(parent_id, "parent@example.com", Role.PARENT, "hash", True),
        User(student_id, "student@example.com", Role.STUDENT, "hash", True),
    ]
    uow = FakeUnitOfWork()
    uow.users = users

    result = asyncio.run(
        LinkParentStudentHandler(lambda: uow).handle(
            LinkParentStudentCommand(parent_id, student_id)
        )
    )

    assert result is True
    users.create_parent_student_link.assert_awaited_once_with(
        parent_id=parent_id, student_id=student_id
    )
    assert uow.exited


@pytest.mark.parametrize(
    ("parent_role", "student_role"),
    [(Role.TEACHER, Role.STUDENT), (Role.PARENT, Role.TEACHER)],
)
def test_link_parent_student_rejects_wrong_role(
    parent_role: Role, student_role: Role
) -> None:
    from gateway_service.application.backoffice import (
        LinkParentStudentCommand,
        LinkParentStudentHandler,
    )
    from gateway_service.application.errors import InvalidParentStudentRolesError

    parent_id, student_id = uuid4(), uuid4()
    users = AsyncMock()
    users.get_by_id.side_effect = [
        User(parent_id, "parent@example.com", parent_role, "hash", True),
        User(student_id, "student@example.com", student_role, "hash", True),
    ]
    uow = FakeUnitOfWork()
    uow.users = users

    with pytest.raises(InvalidParentStudentRolesError):
        asyncio.run(
            LinkParentStudentHandler(lambda: uow).handle(
                LinkParentStudentCommand(parent_id, student_id)
            )
        )

    users.create_parent_student_link.assert_not_awaited()


def test_link_parent_student_rejects_missing_user() -> None:
    from gateway_service.application.backoffice import (
        LinkParentStudentCommand,
        LinkParentStudentHandler,
    )
    from gateway_service.application.errors import UserNotFoundError

    users = AsyncMock()
    users.get_by_id.side_effect = [None, None]
    uow = FakeUnitOfWork()
    uow.users = users

    with pytest.raises(UserNotFoundError):
        asyncio.run(
            LinkParentStudentHandler(lambda: uow).handle(
                LinkParentStudentCommand(uuid4(), uuid4())
            )
        )

    users.create_parent_student_link.assert_not_awaited()
