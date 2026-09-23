from celery import Celery

from document_service.config import DocumentSettings


def create_celery_app(settings: DocumentSettings) -> Celery:
    return Celery("document_service", broker=settings.celery_broker_url)
