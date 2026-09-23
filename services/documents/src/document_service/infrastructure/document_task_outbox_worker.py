import logging
import time

from document_service.application.document_task_outbox_dispatcher import (
    DocumentTaskOutboxDispatcher,
)
from document_service.config import DocumentSettings
from document_service.infrastructure.celery_app import create_celery_app
from document_service.infrastructure.celery_task_publisher import CeleryTaskPublisher
from document_service.infrastructure.database import create_engine, session_factory
from document_service.infrastructure.unit_of_work import SqlAlchemyDocumentUnitOfWork

logger = logging.getLogger(__name__)


def run() -> None:
    settings = DocumentSettings()
    engine = create_engine(settings.document_database_url)
    sessions = session_factory(engine)
    publisher = CeleryTaskPublisher(create_celery_app(settings))
    dispatcher = DocumentTaskOutboxDispatcher(
        uow_factory=lambda: SqlAlchemyDocumentUnitOfWork(sessions),
        publisher=publisher,
    )

    while True:
        try:
            processed = dispatcher.run_once()
        except Exception:
            logger.exception("Document task outbox dispatcher failed")
            time.sleep(1)
            continue

        if processed == 0:
            time.sleep(1)


if __name__ == "__main__":
    run()
