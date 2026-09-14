from pytest import MonkeyPatch


def test_invalidator_settings_reads_only_kafka_and_redis_urls(
    monkeypatch: MonkeyPatch,
) -> None:
    from schedule_service.workers.config import InvalidatorSettings

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    settings = InvalidatorSettings()

    assert settings.kafka_bootstrap_servers == "kafka:19092"
    assert settings.redis_url == "redis://redis:6379/0"
    assert set(InvalidatorSettings.model_fields) == {
        "kafka_bootstrap_servers",
        "redis_url",
    }
