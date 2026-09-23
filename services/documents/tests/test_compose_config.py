from pathlib import Path


def test_document_image_uses_python_313_and_installs_weasyprint_runtime() -> None:
    dockerfile = (Path(__file__).parents[1] / "Dockerfile").read_text()

    assert "FROM python:3.13-slim" in dockerfile
    assert "libpango-1.0-0" in dockerfile


def test_compose_declares_all_document_processes() -> None:
    compose = (Path(__file__).parents[3] / "compose.yaml").read_text()

    for service in (
        "document-migrations:",
        "document-api:",
        "document-dispatcher:",
        "document-worker:",
    ):
        assert service in compose
