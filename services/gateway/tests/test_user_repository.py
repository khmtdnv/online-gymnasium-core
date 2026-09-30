import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from gateway_service.domain.user import Role, User
from gateway_service.infrastructure.models.user import UserRow
from gateway_service.infrastructure.user_repository import SqlAlchemyUserRepository


def test_get_by_email_maps_database_row_to_domain_user() -> None:
    user_id = uuid4()
    row = UserRow(
        id=user_id,
        email="teacher@example.com",
        role="teacher",
        password_hash="stored-hash",
        is_active=True,
    )
    session = AsyncMock(spec=AsyncSession)
    query_result = Mock()
    query_result.scalar_one_or_none.return_value = row
    session.execute.return_value = query_result
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.get_by_email("teacher@example.com"))

    assert result == User(
        id=user_id,
        email="teacher@example.com",
        role=Role.TEACHER,
        password_hash="stored-hash",
        is_active=True,
    )
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert statement.whereclause.right.value == "teacher@example.com"


def test_get_by_id_returns_none_when_user_does_not_exist() -> None:
    user_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    query_result = Mock()
    query_result.scalar_one_or_none.return_value = None
    session.execute.return_value = query_result
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.get_by_id(user_id))

    assert result is None
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    assert statement.whereclause.right.value == user_id


def test_create_user_inserts_domain_values_without_committing() -> None:
    user_id = uuid4()
    user = User(
        id=user_id,
        email="inactive@example.com",
        role=Role.STUDENT,
        password_hash="stored-hash",
        is_active=False,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = user_id
    repository = SqlAlchemyUserRepository(session)

    asyncio.run(repository.create_user(user))

    session.scalar.assert_awaited_once()
    statement = session.scalar.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert compiled.params == {
        "id": user_id,
        "email": "inactive@example.com",
        "role": "student",
        "password_hash": "stored-hash",
        "is_active": False,
    }
    assert "ON CONFLICT ON CONSTRAINT users_email_unique DO NOTHING" in str(compiled)
    assert "RETURNING users.id" in str(compiled)
    session.commit.assert_not_awaited()


def test_create_user_reports_only_named_email_conflict() -> None:
    from gateway_service.application.errors import EmailAlreadyExistsError

    user = User(
        id=uuid4(),
        email="teacher@example.com",
        role=Role.TEACHER,
        password_hash="stored-hash",
        is_active=True,
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    repository = SqlAlchemyUserRepository(session)

    with pytest.raises(EmailAlreadyExistsError):
        asyncio.run(repository.create_user(user))

    statement = session.scalar.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT users_email_unique DO NOTHING" in sql
    assert "RETURNING users.id" in sql
    session.commit.assert_not_awaited()


def test_list_users_maps_all_rows_to_domain_users() -> None:
    first_id = uuid4()
    second_id = uuid4()
    rows = [
        UserRow(
            id=first_id,
            email="student@example.com",
            role="student",
            password_hash="student-hash",
            is_active=True,
        ),
        UserRow(
            id=second_id,
            email="teacher@example.com",
            role="teacher",
            password_hash="teacher-hash",
            is_active=False,
        ),
    ]
    session = AsyncMock(spec=AsyncSession)
    query_result = Mock()
    query_result.scalars.return_value.all.return_value = rows
    session.execute.return_value = query_result
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.list_users())

    assert result == [
        User(
            id=first_id,
            email="student@example.com",
            role=Role.STUDENT,
            password_hash="student-hash",
            is_active=True,
        ),
        User(
            id=second_id,
            email="teacher@example.com",
            role=Role.TEACHER,
            password_hash="teacher-hash",
            is_active=False,
        ),
    ]
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ORDER BY users.email" in sql


def test_create_parent_student_link_inserts_pair_without_committing() -> None:
    parent_id = uuid4()
    student_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = uuid4()
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.create_parent_student_link(parent_id, student_id))

    assert result is True
    session.scalar.assert_awaited_once()
    statement = session.scalar.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert str(compiled).startswith("INSERT INTO parent_student_links ")
    assert (
        "ON CONFLICT ON CONSTRAINT parent_student_links_parent_student_unique DO NOTHING"
        in str(compiled)
    )
    assert "RETURNING parent_student_links.id" in str(compiled)
    assert isinstance(compiled.params["id"], UUID)
    assert compiled.params["parent_id"] == parent_id
    assert compiled.params["student_id"] == student_id
    session.commit.assert_not_awaited()


def test_create_parent_student_link_reports_existing_pair_without_inserting() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.create_parent_student_link(uuid4(), uuid4()))

    assert result is False
    session.commit.assert_not_awaited()


def test_create_refresh_token_stores_jti_and_expiry_without_committing() -> None:
    token_id = uuid4()
    user_id = uuid4()
    expires_at = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)
    session = AsyncMock(spec=AsyncSession)
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.create_refresh_token(token_id, user_id, expires_at))

    assert result is None
    session.execute.assert_awaited_once()
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    assert str(compiled).startswith("INSERT INTO refresh_tokens ")
    assert compiled.params["id"] == token_id
    assert compiled.params["user_id"] == user_id
    assert compiled.params["expires_at"] == expires_at
    session.commit.assert_not_awaited()


def test_consume_refresh_token_claims_only_matching_live_unused_token() -> None:
    token_id = uuid4()
    user_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = token_id
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.consume_refresh_token(token_id, user_id))

    assert result is True
    session.scalar.assert_awaited_once()
    statement = session.scalar.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert sql.startswith("UPDATE refresh_tokens SET consumed_at=now()")
    assert "refresh_tokens.id =" in sql
    assert "refresh_tokens.user_id =" in sql
    assert "refresh_tokens.consumed_at IS NULL" in sql
    assert "refresh_tokens.expires_at > now()" in sql
    assert "RETURNING refresh_tokens.id" in sql
    assert token_id in compiled.params.values()
    assert user_id in compiled.params.values()
    session.commit.assert_not_awaited()


def test_consume_refresh_token_returns_false_when_no_row_was_updated() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = None
    repository = SqlAlchemyUserRepository(session)

    result = asyncio.run(repository.consume_refresh_token(uuid4(), uuid4()))

    assert result is False
    session.commit.assert_not_awaited()
