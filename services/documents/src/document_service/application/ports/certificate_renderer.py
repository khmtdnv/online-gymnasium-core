from typing import Protocol

from document_service.domain.certificate import CertificateData


class CertificateRenderer(Protocol):
    def render(self, certificate: CertificateData) -> bytes: ...
