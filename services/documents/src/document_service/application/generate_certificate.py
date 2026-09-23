from dataclasses import dataclass
from uuid import UUID

from document_service.application.ports.certificate_renderer import CertificateRenderer
from document_service.application.ports.document_storage import DocumentStorage
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory
from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentStatus


@dataclass(frozen=True, slots=True)
class GenerateCertificateCommand:
    job_id: UUID


class GenerateCertificateHandler:
    def __init__(
        self,
        uow_factory: DocumentUnitOfWorkFactory,
        renderer: CertificateRenderer,
        storage: DocumentStorage,
    ) -> None:
        self._uow_factory = uow_factory
        self._renderer = renderer
        self._storage = storage

    def handle(self, command: GenerateCertificateCommand) -> None:
        with self._uow_factory() as uow:
            job = uow.documents.get_job(command.job_id)

            if job is None:
                return

            if job.status is DocumentStatus.COMPLETED:
                return

            uow.documents.mark_processing(command.job_id)

        certificate = CertificateData(
            student_full_name=job.payload["student_full_name"],
            class_name=job.payload["class_name"],
            academic_year=job.payload["academic_year"],
        )
        pdf_bytes = self._renderer.render(certificate)

        object_key = f"certificates/{command.job_id}.pdf"
        self._storage.put_pdf(object_key, pdf_bytes)

        with self._uow_factory() as uow:
            uow.documents.mark_completed(command.job_id, object_key)
