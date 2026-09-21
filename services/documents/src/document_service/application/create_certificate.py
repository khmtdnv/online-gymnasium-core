from dataclasses import dataclass

from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory
from document_service.domain.certificate import CertificateData
from document_service.domain.document import DocumentJob


@dataclass(frozen=True, slots=True)
class CreateCertificateCommand:
    student_full_name: str
    class_name: str
    academic_year: str


class CreateCertificateHandler:
    def __init__(self, uow_factory: DocumentUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def handle(self, command: CreateCertificateCommand) -> DocumentJob:
        certificate = CertificateData(
            student_full_name=command.student_full_name,
            class_name=command.class_name,
            academic_year=command.academic_year,
        )
        with self._uow_factory() as uow:
            return uow.documents.create_job_with_outbox(certificate)
