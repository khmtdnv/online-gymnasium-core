from pytest import MonkeyPatch


def test_relay_settings_reads_database_and_kafka_urls_from_environment(monkeypatch: MonkeyPatch) -> None:
    from schedule_service.workers.config import RelaySettings

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://schedule:password@postgres:5432/schedule")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")

    settings = RelaySettings()

    assert settings.database_url == "postgresql+asyncpg://schedule:password@postgres:5432/schedule"
    assert settings.kafka_bootstrap_servers == "kafka:19092"
