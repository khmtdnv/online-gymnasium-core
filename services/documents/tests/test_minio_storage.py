from unittest.mock import Mock

import pytest

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
