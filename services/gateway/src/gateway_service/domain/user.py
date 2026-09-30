from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    STUDENT = "student"
    TEACHER = "teacher"
    PARENT = "parent"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class User:
    id: UUID
    email: str
    role: Role
    password_hash: str
    is_active: bool
