from pathlib import Path

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape
from weasyprint import HTML

from document_service.domain.certificate import CertificateData


class WeasyPrintCertificateRenderer:
    def __init__(self, template: Template) -> None:
        self._template = template

    def render(self, certificate: CertificateData) -> bytes:
        rendered_template = self._template.render(
            student_full_name=certificate.student_full_name,
            class_name=certificate.class_name,
            academic_year=certificate.academic_year,
        )

        return HTML(string=rendered_template).write_pdf()


def create_certificate_renderer(
    template_directory: Path,
) -> WeasyPrintCertificateRenderer:
    environment = Environment(
        loader=FileSystemLoader(template_directory),
        autoescape=select_autoescape(["html"]),
    )
    template = environment.get_template("certificate.html")
    return WeasyPrintCertificateRenderer(template)
