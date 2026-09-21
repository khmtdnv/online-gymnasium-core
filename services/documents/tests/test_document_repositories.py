from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentStatus
from document_service.infrastructure.models.document_job import DocumentJobRow
from document_service.infrastructure.models.document_task_outbox import (
    DocumentTaskOutboxRow,
)


def test_repository_adds_pending_job_and_one_matching_outbox_row() -> None:
    from document_service.infrastructure.repositories import (
        SqlAlchemyDocumentRepository,
    )

    session = Mock(spec=Session)

    def assign_database_timestamp(row: DocumentJobRow) -> None:
        row.created_at = datetime(2026, 9, 21, tzinfo=UTC)

    session.refresh.side_effect = assign_database_timestamp
    repository = SqlAlchemyDocumentRepository(session)

    result = repository.create_job_with_outbox(
        CertificateData(
            student_full_name="Иван Петров",
            class_name="7А",
            academic_year="2026/2027",
        )
    )

    rows = session.add_all.call_args.args[0]
    job_row = next(row for row in rows if isinstance(row, DocumentJobRow))
    outbox_row = next(row for row in rows if isinstance(row, DocumentTaskOutboxRow))

    assert isinstance(job_row.id, UUID)
    assert job_row.document_type == "certificate"
    assert job_row.status == "pending"
    assert job_row.payload == {
        "student_full_name": "Иван Петров",
        "class_name": "7А",
        "academic_year": "2026/2027",
    }
    assert outbox_row.document_job_id == job_row.id
    assert outbox_row.task_name == "documents.generate_certificate"
    session.flush.assert_called_once()
    session.refresh.assert_called_once_with(job_row)
    assert result.id == job_row.id
    assert result.status is DocumentStatus.PENDING
    assert result.created_at == datetime(2026, 9, 21, tzinfo=UTC)


def test_uow_commits_and_closes_session_after_success() -> None:
    from document_service.infrastructure.uow import SqlAlchemyDocumentUnitOfWork

    session = Mock(spec=Session)
    uow = SqlAlchemyDocumentUnitOfWork(session_factory=lambda: session)

    with uow as active_uow:
        assert active_uow.documents is not None

    session.commit.assert_called_once()
    session.rollback.assert_not_called()
    session.close.assert_called_once()


def test_uow_rolls_back_and_closes_session_after_error() -> None:
    from document_service.infrastructure.uow import SqlAlchemyDocumentUnitOfWork

    session = Mock(spec=Session)
    uow = SqlAlchemyDocumentUnitOfWork(session_factory=lambda: session)

    with pytest.raises(RuntimeError, match="boom"), uow:
        raise RuntimeError("boom")

    session.commit.assert_not_called()
    session.rollback.assert_called_once()
    session.close.assert_called_once()
