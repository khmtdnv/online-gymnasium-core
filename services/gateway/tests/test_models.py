from sqlalchemy import CheckConstraint, UniqueConstraint

from gateway_service.infrastructure.models.parent_student_link import (
    ParentStudentLinkRow,
)
from gateway_service.infrastructure.models.refresh_token import RefreshTokenRow
from gateway_service.infrastructure.models.user import UserRow


def test_user_row_has_named_email_and_role_constraints() -> None:
    constraints = UserRow.__table__.constraints
    unique_constraints = [
        constraint
        for constraint in constraints
        if isinstance(constraint, UniqueConstraint)
    ]
    role_constraint = next(
        constraint
        for constraint in constraints
        if isinstance(constraint, CheckConstraint)
    )

    assert any(
        tuple(column.name for column in constraint.columns) == ("email",)
        and constraint.name == "users_email_unique"
        for constraint in unique_constraints
    )
    assert "role IN ('student', 'teacher', 'parent', 'admin')" == str(
        role_constraint.sqltext
    )
    assert UserRow.__table__.c.is_active.server_default is not None
    assert UserRow.__table__.c.created_at.server_default is not None
    assert UserRow.__table__.c.updated_at.onupdate is not None


def test_refresh_token_row_uses_its_primary_key_as_the_future_jti() -> None:
    table = RefreshTokenRow.__table__

    assert tuple(table.primary_key.columns.keys()) == ("id",)
    assert "jti" not in table.c
    assert len(table.foreign_keys) == 1
    assert next(iter(table.foreign_keys)).target_fullname == "users.id"
    assert table.c.consumed_at.nullable is True
    assert table.c.created_at.server_default is not None


def test_parent_student_link_row_prevents_duplicate_links() -> None:
    table = ParentStudentLinkRow.__table__
    unique_constraint = next(
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    )

    assert tuple(unique_constraint.columns.keys()) == ("parent_id", "student_id")
    assert unique_constraint.name == "parent_student_links_parent_student_unique"
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "users.id"
    }
    assert table.c.created_at.server_default is not None
