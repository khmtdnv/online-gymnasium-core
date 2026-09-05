from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    app_name: str = "OG1 Schedule Service"

    database_url: str
    redis_url: str
    rabbitmq_url: str
