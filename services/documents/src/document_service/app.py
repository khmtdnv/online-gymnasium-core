from fastapi import FastAPI

from document_service.api.router import router
from document_service.application.ports.document_storage import DocumentStorage
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory
from document_service.config import DocumentSettings


def create_app(
    settings: DocumentSettings,
    uow_factory: DocumentUnitOfWorkFactory,
    storage: DocumentStorage,
) -> FastAPI:
    app = FastAPI(title="Document Service")
    app.include_router(router)
    app.state.settings = settings
    app.state.uow_factory = uow_factory
    app.state.storage = storage
    return app
