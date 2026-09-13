import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiokafka import AIOKafkaProducer
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.mark.anyio
async def test_worker_starts_and_stops_kafka_and_database_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    from schedule_service.workers import outbox_relay

    producer = AsyncMock(spec=AIOKafkaProducer)
    engine = AsyncMock(spec=AsyncEngine)
    relay = AsyncMock()
    relay.run_once.return_value = 0
    settings = SimpleNamespace(
        database_url="postgresql+asyncpg://schedule:password@postgres:5432/schedule",
        kafka_bootstrap_servers="kafka:19092",
    )

    monkeypatch.setattr(outbox_relay, "RelaySettings", lambda: settings)
    monkeypatch.setattr(outbox_relay, "create_engine", lambda url: engine)
    monkeypatch.setattr(outbox_relay, "create_session_factory", lambda _: object())
    monkeypatch.setattr(outbox_relay, "AIOKafkaProducer", lambda **_: producer)
    monkeypatch.setattr(outbox_relay, "OutboxRelay", lambda **_: relay)

    async def stop_loop(_: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(outbox_relay.asyncio, "sleep", stop_loop)

    with pytest.raises(asyncio.CancelledError):
        await outbox_relay.run()

    producer.start.assert_awaited_once()
    producer.stop.assert_awaited_once()
    engine.dispose.assert_awaited_once()
