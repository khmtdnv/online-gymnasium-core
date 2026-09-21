from collections.abc import Callable
from typing import Self

from sqlalchemy.orm import Session

from document_service.infrastructure.repositories import SqlAlchemyDocumentRepository

type SessionFactory = Callable[[], Session]


class SqlAlchemyDocumentUnitOfWork:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self.documents = SqlAlchemyDocumentRepository(self._session)
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
