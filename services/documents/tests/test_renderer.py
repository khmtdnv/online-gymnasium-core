from jinja2 import Template

from document_service.domain.certificate import CertificateData
from document_service.infrastructure.renderer import WeasyPrintCertificateRenderer


def test_renderer_returns_pdf_bytes_from_certificate_data() -> None:
    renderer = WeasyPrintCertificateRenderer(
        Template("<h1>{{ student_full_name }}</h1><p>{{ class_name }}</p>")
    )

    pdf_bytes = renderer.render(CertificateData("Иван Петров", "7А", "2026/2027"))

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 0
