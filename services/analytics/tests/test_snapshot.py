from datetime import UTC, datetime

import pytest


def lesson_snapshot_envelope() -> dict[str, object]:
    return {
        "event_id": 42,
        "event_type": "lesson.snapshot",
        "occurred_at": "2026-09-19T10:00:00+00:00",
        "payload": {
            "lesson_id": 501,
            "class_id": 10,
            "teacher_id": 100,
            "subject_id": 1000,
            "starts_at": "2026-09-20T10:00:00+00:00",
            "ends_at": "2026-09-20T11:30:00+00:00",
            "status": "planned",
            "version": 3,
        },
    }


def test_parses_documented_lesson_snapshot_envelope() -> None:
    from analytics_service.application.snapshot import (
        LessonSnapshot,
        parse_lesson_snapshot,
    )

    snapshot = parse_lesson_snapshot(lesson_snapshot_envelope())

    assert snapshot == LessonSnapshot(
        event_id=42,
        occurred_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
        lesson_id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 20, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 20, 11, 30, tzinfo=UTC),
        status="planned",
        version=3,
    )


def test_ignores_unrelated_event() -> None:
    from analytics_service.application.snapshot import parse_lesson_snapshot

    result = parse_lesson_snapshot(
        {
            "event_id": 43,
            "event_type": "schedule.changed",
            "occurred_at": "2026-09-19T10:00:00+00:00",
            "payload": {"lesson_id": 501},
        }
    )

    assert result is None


def test_rejects_lesson_snapshot_without_required_value() -> None:
    from analytics_service.application.snapshot import parse_lesson_snapshot

    envelope = lesson_snapshot_envelope()
    payload = envelope["payload"]
    assert isinstance(payload, dict)
    del payload["version"]

    with pytest.raises(ValueError, match="version"):
        parse_lesson_snapshot(envelope)


def test_rejects_lesson_snapshot_with_non_object_payload() -> None:
    from analytics_service.application.snapshot import parse_lesson_snapshot

    envelope = lesson_snapshot_envelope()
    envelope["payload"] = []

    with pytest.raises(TypeError, match="payload"):
        parse_lesson_snapshot(envelope)
