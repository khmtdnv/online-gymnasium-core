from pytest import MonkeyPatch


def test_settings_object_created_from_env(monkeypatch: MonkeyPatch) -> None:

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://schedule:password@localhost:5432/schedule",
    )
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

    from schedule_service.config import Settings

    settings = Settings()

    assert (
        settings.database_url
        == "postgresql+asyncpg://schedule:password@localhost:5432/schedule"
    )
