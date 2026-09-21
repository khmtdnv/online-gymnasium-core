from collections.abc import Callable
from typing import Protocol, Self

from document_service.application.ports.document_repository import DocumentRepository


class DocumentUnitOfWork(Protocol):
    documents: DocumentRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None: ...


type DocumentUnitOfWorkFactory = Callable[[], DocumentUnitOfWork]
