from unittest.mock import Mock

import pytest


def test_worker_retries_dispatch_loop_after_broker_error(monkeypatch) -> None:
    from document_service.infrastructure import document_task_outbox_worker as worker

    settings = Mock()
    settings.document_database_url = "sqlite://"
    settings.celery_broker_url = "amqp://guest:guest@localhost:5672//"
    engine = object()
    session_factory = object()
    celery_app = object()
    publisher = object()

    dispatcher = Mock()
    dispatcher.run_once.side_effect = ConnectionError("RabbitMQ is unavailable")

    monkeypatch.setattr(worker, "DocumentSettings", lambda: settings)
    monkeypatch.setattr(worker, "create_engine", lambda _: engine)
    monkeypatch.setattr(worker, "session_factory", lambda _: session_factory)
    monkeypatch.setattr(worker, "create_celery_app", lambda _: celery_app)
    monkeypatch.setattr(worker, "CeleryTaskPublisher", lambda _: publisher)
    monkeypatch.setattr(worker, "DocumentTaskOutboxDispatcher", lambda **_: dispatcher)

    def stop_loop(_: float) -> None:
        raise RuntimeError("stop loop")

    monkeypatch.setattr(worker.time, "sleep", stop_loop)

    with pytest.raises(RuntimeError, match="stop loop"):
        worker.run()

    dispatcher.run_once.assert_called_once()


def test_worker_polls_again_immediately_after_dispatching_a_task(monkeypatch) -> None:
    from document_service.infrastructure import document_task_outbox_worker as worker

    settings = Mock()
    settings.document_database_url = "sqlite://"
    settings.celery_broker_url = "amqp://guest:guest@localhost:5672//"
    dispatcher = Mock()
    dispatcher.run_once.side_effect = [1, 0]

    monkeypatch.setattr(worker, "DocumentSettings", lambda: settings)
    monkeypatch.setattr(worker, "create_engine", lambda _: object())
    monkeypatch.setattr(worker, "session_factory", lambda _: object())
    monkeypatch.setattr(worker, "create_celery_app", lambda _: object())
    monkeypatch.setattr(worker, "CeleryTaskPublisher", lambda _: object())
    monkeypatch.setattr(worker, "DocumentTaskOutboxDispatcher", lambda **_: dispatcher)

    def stop_loop(_: float) -> None:
        raise RuntimeError("stop loop")

    monkeypatch.setattr(worker.time, "sleep", stop_loop)

    with pytest.raises(RuntimeError, match="stop loop"):
        worker.run()

    assert dispatcher.run_once.call_count == 2
