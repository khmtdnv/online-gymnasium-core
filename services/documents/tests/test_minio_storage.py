from unittest.mock import Mock

import pytest
from minio.error import ServerError
from urllib3.exceptions import HTTPError

from document_service.application.errors import TemporaryStorageError
from document_service.infrastructure.minio_storage import MinioDocumentStorage


def test_storage_reads_object_and_releases_minio_connection() -> None:
    client = Mock()
    response = Mock()
    response.read.return_value = b"%PDF-1.7\ncertificate"
    client.get_object.return_value = response
    storage = MinioDocumentStorage(client=client, bucket="documents")

    result = storage.read("certificates/501.pdf")

    assert result == b"%PDF-1.7\ncertificate"
    client.get_object.assert_called_once_with("documents", "certificates/501.pdf")
    response.close.assert_called_once_with()
    response.release_conn.assert_called_once_with()


def test_storage_releases_minio_connection_when_read_fails() -> None:
    client = Mock()
    response = Mock()
    response.read.side_effect = OSError("MinIO connection interrupted")
    client.get_object.return_value = response
    storage = MinioDocumentStorage(client=client, bucket="documents")

    with pytest.raises(OSError, match="interrupted"):
        storage.read("certificates/501.pdf")

    response.close.assert_called_once_with()
    response.release_conn.assert_called_once_with()


@pytest.mark.parametrize(
    "storage_error",
    [
        ServerError("MinIO is unavailable", 503),
        HTTPError("network connection was interrupted"),
    ],
)
def test_storage_translates_temporary_upload_errors(
    storage_error: Exception,
) -> None:
    client = Mock()
    client.put_object.side_effect = storage_error
    storage = MinioDocumentStorage(client=client, bucket="documents")

    with pytest.raises(TemporaryStorageError) as error:
        storage.put_pdf("certificates/501.pdf", b"%PDF-1.7\ncertificate")

    assert error.value.__cause__ is storage_error
