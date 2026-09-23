from io import BytesIO

from minio import Minio
from minio.error import ServerError
from urllib3.exceptions import HTTPError

from document_service.application.errors import TemporaryStorageError


class MinioDocumentStorage:
    def __init__(self, client: Minio, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def read(self, object_key: str) -> bytes:
        minio_response = self._client.get_object(self._bucket, object_key)

        try:
            return minio_response.read()
        finally:
            minio_response.close()
            minio_response.release_conn()

    def put_pdf(self, object_key: str, pdf_bytes: bytes) -> None:
        try:
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=object_key,
                data=BytesIO(pdf_bytes),
                length=len(pdf_bytes),
                content_type="application/pdf",
            )
        except (HTTPError, ServerError) as exc:
            raise TemporaryStorageError from exc
