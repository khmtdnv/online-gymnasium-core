from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from gateway_service.application.errors import EmailAlreadyExistsError
from gateway_service.domain.user import Role, User
from gateway_service.infrastructure.models.parent_student_link import (
    ParentStudentLinkRow,
)
from gateway_service.infrastructure.models.refresh_token import RefreshTokenRow
from gateway_service.infrastructure.models.user import UserRow


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _to_domain_model(db_model: UserRow) -> User:
        return User(
            id=db_model.id,
            email=db_model.email,
            role=Role(db_model.role),
            password_hash=db_model.password_hash,
            is_active=db_model.is_active,
        )

    async def get_by_id(self, user_id: UUID) -> User | None:
        statement = select(UserRow).where(UserRow.id == user_id)
        row = await self._session.execute(statement)
        result = row.scalar_one_or_none()

        if result is None:
            return

        return self._to_domain_model(result)

    async def get_by_email(self, email: str) -> User | None:
        statement = select(UserRow).where(UserRow.email == email)
        row = await self._session.execute(statement)
        result = row.scalar_one_or_none()

        if result is None:
            return

        return self._to_domain_model(result)

    async def create_user(self, user: User) -> None:
        statement = (
            insert(UserRow)
            .values(
                id=user.id,
                email=user.email,
                role=user.role.value,
                password_hash=user.password_hash,
                is_active=user.is_active,
            )
            .on_conflict_do_nothing(constraint="users_email_unique")
            .returning(UserRow.id)
        )
        result = await self._session.scalar(statement)
        if result is None:
            raise EmailAlreadyExistsError

    async def list_users(self) -> list[User]:
        statement = select(UserRow).order_by(UserRow.email)
        rows = await self._session.execute(statement)
        results_list = rows.scalars().all()

        users_list = []
        for result in results_list:
            users_list.append(self._to_domain_model(result))

        return users_list

    async def create_parent_student_link(
        self,
        parent_id: UUID,
        student_id: UUID,
    ) -> bool:
        statement = (
            insert(ParentStudentLinkRow)
            .values(id=uuid4(), parent_id=parent_id, student_id=student_id)
            .on_conflict_do_nothing(
                constraint="parent_student_links_parent_student_unique"
            )
            .returning(ParentStudentLinkRow.id)
        )
        inserted_id = await self._session.scalar(statement)
        return inserted_id is not None

    async def create_refresh_token(
        self, token_id: UUID, user_id: UUID, expires_at: datetime
    ) -> None:
        statement = insert(RefreshTokenRow).values(
            id=token_id, user_id=user_id, expires_at=expires_at
        )
        await self._session.execute(statement)

    async def consume_refresh_token(self, token_id: UUID, user_id: UUID) -> bool:
        statement = (
            update(RefreshTokenRow)
            .values(consumed_at=func.now())
            .where(
                RefreshTokenRow.id == token_id,
                RefreshTokenRow.user_id == user_id,
                RefreshTokenRow.expires_at > func.now(),
                RefreshTokenRow.consumed_at.is_(None),
            )
            .returning(RefreshTokenRow.id)
        )
        updated_id = await self._session.scalar(statement)
        return updated_id is not None
