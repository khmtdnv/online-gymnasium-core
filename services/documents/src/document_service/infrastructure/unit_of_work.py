from collections.abc import Callable
from typing import Self

from sqlalchemy.orm import Session

from document_service.infrastructure.document_repository import (
    SqlAlchemyDocumentRepository,
)
from document_service.infrastructure.document_task_outbox_repository import (
    SqlAlchemyDocumentTaskOutboxRepository,
)

type SessionFactory = Callable[[], Session]


class SqlAlchemyDocumentUnitOfWork:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.documents = SqlAlchemyDocumentRepository(self._session)
        self.outbox = SqlAlchemyDocumentTaskOutboxRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
