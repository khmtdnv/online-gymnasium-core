from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from document_service.infrastructure.models.document_task_outbox import (
    DocumentTaskOutboxRow,
)


def test_repository_returns_unpublished_tasks_in_creation_order() -> None:
    from document_service.infrastructure.document_task_outbox_repository import (
        SqlAlchemyDocumentTaskOutboxRepository,
    )

    first = DocumentTaskOutboxRow(
        id=uuid4(),
        document_job_id=uuid4(),
        task_name="documents.generate_certificate",
        created_at=datetime(2026, 9, 22, 10, tzinfo=UTC),
    )
    second = DocumentTaskOutboxRow(
        id=uuid4(),
        document_job_id=uuid4(),
        task_name="documents.generate_certificate",
        created_at=datetime(2026, 9, 22, 11, tzinfo=UTC),
    )
    session = Mock(spec=Session)
    session.scalars.return_value.all.return_value = [first, second]
    repository = SqlAlchemyDocumentTaskOutboxRepository(session)

    tasks = repository.get_pending(limit=100)

    assert [task.id for task in tasks] == [first.id, second.id]
    statement = session.scalars.call_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "document_task_outbox.published_at IS NULL" in sql
    assert "ORDER BY document_task_outbox.created_at" in sql
    assert "LIMIT 100" in sql


def test_repository_marks_only_unpublished_task_as_published() -> None:
    from document_service.infrastructure.document_task_outbox_repository import (
        SqlAlchemyDocumentTaskOutboxRepository,
    )

    task_id = uuid4()
    session = Mock(spec=Session)
    repository = SqlAlchemyDocumentTaskOutboxRepository(session)

    repository.mark_published(task_id=task_id)

    statement = session.execute.call_args.args[0]
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "UPDATE document_task_outbox SET published_at=now()" in sql
    assert str(task_id) in sql
    assert "document_task_outbox.published_at IS NULL" in sql
