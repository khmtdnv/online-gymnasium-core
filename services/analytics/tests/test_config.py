def test_analytics_settings_read_kafka_and_clickhouse_values_from_environment(
    monkeypatch,
) -> None:
    from analytics_service.config import AnalyticsSettings

    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:19092")
    monkeypatch.setenv("CLICKHOUSE_HOST", "clickhouse")
    monkeypatch.setenv("CLICKHOUSE_PORT", "8123")
    monkeypatch.setenv("CLICKHOUSE_USER", "default")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "change-me")

    settings = AnalyticsSettings()

    assert settings.kafka_bootstrap_servers == "kafka:19092"
    assert settings.clickhouse_host == "clickhouse"
    assert settings.clickhouse_port == 8123
    assert settings.clickhouse_user == "default"
    assert settings.clickhouse_password == "change-me"


def test_analytics_api_settings_read_clickhouse_values_from_environment(
    monkeypatch,
) -> None:
    from analytics_service.config import AnalyticsApiSettings

    monkeypatch.setenv("CLICKHOUSE_HOST", "clickhouse")
    monkeypatch.setenv("CLICKHOUSE_PORT", "8123")
    monkeypatch.setenv("CLICKHOUSE_USER", "default")
    monkeypatch.setenv("CLICKHOUSE_PASSWORD", "change-me")

    settings = AnalyticsApiSettings()

    assert settings.clickhouse_host == "clickhouse"
    assert settings.clickhouse_port == 8123
    assert settings.clickhouse_user == "default"
    assert settings.clickhouse_password == "change-me"
