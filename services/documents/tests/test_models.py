from sqlalchemy import CheckConstraint


def test_document_models_expose_expected_table_names() -> None:
    from document_service.infrastructure.models.document_job import DocumentJobRow
    from document_service.infrastructure.models.document_task_outbox import (
        DocumentTaskOutboxRow,
    )

    assert DocumentJobRow.__tablename__ == "document_jobs"
    assert DocumentTaskOutboxRow.__tablename__ == "document_task_outbox"


def test_document_job_status_is_constrained_and_outbox_has_one_task_contract() -> None:
    from document_service.infrastructure.models.document_job import DocumentJobRow
    from document_service.infrastructure.models.document_task_outbox import (
        DocumentTaskOutboxRow,
    )

    constraints = DocumentJobRow.__table__.constraints

    assert any(
        isinstance(constraint, CheckConstraint)
        and constraint.name == "document_jobs_valid_status"
        for constraint in constraints
    )
    assert "document_type" not in DocumentTaskOutboxRow.__table__.c
    assert (
        DocumentTaskOutboxRow.__table__.c.task_name.server_default.arg
        == "documents.generate_certificate"
    )
    assert {index.name for index in DocumentTaskOutboxRow.__table__.indexes} == {
        "document_task_outbox_unpublished_created_at_idx"
    }
