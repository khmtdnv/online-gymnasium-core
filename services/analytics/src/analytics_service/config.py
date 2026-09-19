from pydantic_settings import BaseSettings, SettingsConfigDict


class AnalyticsSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    kafka_bootstrap_servers: str

    clickhouse_user: str
    clickhouse_password: str
    clickhouse_host: str
    clickhouse_port: int

    analytics_dlq_topic: str


class AnalyticsApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    clickhouse_host: str
    clickhouse_port: int
    clickhouse_user: str
    clickhouse_password: str
