from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from gateway_service.domain.user import Role, User


@dataclass(frozen=True, slots=True)
class DecodedRefresh:
    """Результат проверки старого токена."""

    user_id: UUID
    jti: UUID


@dataclass(frozen=True, slots=True)
class DecodedAccess:
    """Результат проверки access токена."""

    user_id: UUID
    role: Role


@dataclass(frozen=True, slots=True)
class IssuedRefresh:
    """Результат выпуска нового токена."""

    token: str
    jti: UUID
    expires_at: datetime


class TokenService(Protocol):
    def decode_refresh(self, token: str) -> DecodedRefresh: ...

    def decode_access(self, token: str) -> DecodedAccess: ...

    def issue_refresh(self, user: User) -> IssuedRefresh: ...

    def issue_access(self, user: User) -> str: ...
