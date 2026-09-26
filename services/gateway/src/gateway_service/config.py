from pydantic_settings import BaseSettings, SettingsConfigDict


class GatewaySettings(BaseSettings):
    database_url: str
    jwt_secret: str
    backoffice_service_token: str
    access_token_ttl_seconds: int = 15 * 60
    refresh_token_ttl_seconds: int = 7 * 24 * 60 * 60

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
