from datetime import datetime
from typing import Protocol
from uuid import UUID

from gateway_service.domain.user import User


class UserRepository(Protocol):
    async def get_by_id(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def create_user(self, user: User) -> None: ...

    async def list_users(self) -> list[User]: ...

    async def create_parent_student_link(
        self, parent_id: UUID, student_id: UUID
    ) -> bool: ...

    async def create_refresh_token(
        self, token_id: UUID, user_id: UUID, expires_at: datetime
    ) -> None: ...

    async def consume_refresh_token(self, token_id: UUID, user_id: UUID) -> bool: ...
