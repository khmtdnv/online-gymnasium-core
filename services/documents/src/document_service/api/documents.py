from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from pydantic import BaseModel

from document_service.api.dependencies import (
    get_create_certificate_handler,
    get_document_storage,
    get_uow_factory,
)
from document_service.application.create_certificate import (
    CreateCertificateCommand,
    CreateCertificateHandler,
)
from document_service.application.ports.document_storage import DocumentStorage
from document_service.application.ports.unit_of_work import DocumentUnitOfWorkFactory
from document_service.domain.certificate import InvalidCertificateData
from document_service.domain.document import DocumentJob, DocumentStatus

router = APIRouter(prefix="/documents", tags=["documents"])


class CreateCertificateRequest(BaseModel):
    student_full_name: str
    class_name: str
    academic_year: str


class CreatedDocumentResponse(BaseModel):
    id: UUID
    document_type: str
    status: str


class DocumentStatusResponse(BaseModel):
    id: UUID
    document_type: str
    status: str
    created_at: datetime
    download_url: str | None = None


def _get_document_or_404(
    *,
    job_id: UUID,
    uow_factory: DocumentUnitOfWorkFactory,
) -> DocumentJob:
    with uow_factory() as uow:
        job = uow.documents.get_job(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Document was not found")

    return job


@router.post(
    "/certificates",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreatedDocumentResponse,
)
def create_certificate(
    request_model: CreateCertificateRequest,
    handler: Annotated[
        CreateCertificateHandler,
        Depends(get_create_certificate_handler),
    ],
) -> CreatedDocumentResponse:
    command = CreateCertificateCommand(
        student_full_name=request_model.student_full_name,
        class_name=request_model.class_name,
        academic_year=request_model.academic_year,
    )
    try:
        job = handler.handle(command)
    except InvalidCertificateData as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Certificate data must not be blank",
        ) from exc

    return CreatedDocumentResponse(
        id=job.id,
        document_type=job.document_type,
        status=job.status.value,
    )


@router.get(
    "/{job_id}",
    response_model=DocumentStatusResponse,
    response_model_exclude_none=True,
)
def get_document(
    job_id: UUID,
    uow_factory: Annotated[DocumentUnitOfWorkFactory, Depends(get_uow_factory)],
) -> DocumentStatusResponse:
    job = _get_document_or_404(job_id=job_id, uow_factory=uow_factory)
    download_url = None
    if job.status is DocumentStatus.COMPLETED:
        download_url = f"/documents/{job.id}/content"

    return DocumentStatusResponse(
        id=job.id,
        document_type=job.document_type,
        status=job.status.value,
        created_at=job.created_at,
        download_url=download_url,
    )


@router.get("/{job_id}/content")
def get_document_content(
    job_id: UUID,
    uow_factory: Annotated[DocumentUnitOfWorkFactory, Depends(get_uow_factory)],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
) -> Response:
    job = _get_document_or_404(job_id=job_id, uow_factory=uow_factory)

    if job.status in {DocumentStatus.PENDING, DocumentStatus.PROCESSING}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document is not ready",
        )

    if job.status is DocumentStatus.FAILED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document generation failed",
        )

    assert job.object_key is not None
    return Response(
        storage.read(job.object_key),
        media_type="application/pdf",
    )
