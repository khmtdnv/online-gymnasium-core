from fastapi import Request

from document_service.application.create_certificate import CreateCertificateHandler
from document_service.application.ports.document_storage import DocumentStorage
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory


def get_create_certificate_handler(request: Request) -> CreateCertificateHandler:
    uow_factory: DocumentUnitOfWorkFactory = request.app.state.uow_factory
    return CreateCertificateHandler(uow_factory=uow_factory)


def get_uow_factory(request: Request) -> DocumentUnitOfWorkFactory:
    return request.app.state.uow_factory


def get_document_storage(request: Request) -> DocumentStorage:
    return request.app.state.storage
