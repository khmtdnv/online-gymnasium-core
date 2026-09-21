from pydantic_settings import BaseSettings, SettingsConfigDict


class DocumentSettings(BaseSettings):
    document_database_url: str
    celery_broker_url: str
    minio_endpoint: str
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documents"
    minio_secure: bool = False

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
