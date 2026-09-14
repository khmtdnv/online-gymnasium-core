from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    app_name: str = "OG1 Schedule Service"

    database_url: str
    redis_url: str
    rabbitmq_url: str
    schedule_cache_ttl_seconds: int = Field(gt=0, default=60)
    schedule_cache_lock_ttl_ms: int = Field(gt=0, default=5000)
    schedule_cache_lock_retry_delay_ms: int = Field(gt=0, default=50)
    schedule_cache_lock_retry_limit: int = Field(gt=0, default=20)
