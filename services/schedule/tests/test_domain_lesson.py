from datetime import UTC, datetime

import pytest

from schedule_service.domain.lesson import (
    InvalidLessonInterval,
    Lesson,
    LessonAlreadyCanceled,
)


def test_valid_data_created_valid_domain_object() -> None:
    domain_object = Lesson.create(
        class_id=1,
        teacher_id=1,
        subject_id=1,
        starts_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
    )

    assert domain_object.id is None
    assert domain_object.status == "planned"
    assert domain_object.version == 1


def test_invalid_timerange_raises_domain_error() -> None:
    with pytest.raises(InvalidLessonInterval):
        Lesson.create(
            class_id=1,
            teacher_id=1,
            subject_id=1,
            starts_at=datetime(2026, 9, 10, 12, 15, tzinfo=UTC),
            ends_at=datetime(2026, 9, 10, 11, 30, tzinfo=UTC),
        )


def test_equal_timerange_raises_domain_error() -> None:
    instant = datetime(2026, 9, 10, 12, 15, tzinfo=UTC)

    with pytest.raises(InvalidLessonInterval):
        Lesson.create(
            class_id=1,
            teacher_id=1,
            subject_id=1,
            starts_at=instant,
            ends_at=instant,
        )


def test_create_rejects_lesson_crossing_midnight() -> None:
    with pytest.raises(InvalidLessonInterval):
        Lesson.create(
            class_id=10,
            teacher_id=100,
            subject_id=1000,
            starts_at=datetime(2026, 9, 10, 23, tzinfo=UTC),
            ends_at=datetime(2026, 9, 11, 1, tzinfo=UTC),
        )


def test_reschedule_rejects_lesson_crossing_midnight() -> None:
    lesson = Lesson.create(
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
    )

    with pytest.raises(InvalidLessonInterval):
        lesson.reschedule(
            starts_at=datetime(2026, 9, 10, 23, tzinfo=UTC),
            ends_at=datetime(2026, 9, 11, 1, tzinfo=UTC),
        )


def test_reschedule_changes_interval_and_preserves_other_lesson_data() -> None:
    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="planned",
        version=3,
    )

    lesson.reschedule(
        starts_at=datetime(2026, 9, 10, 12, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 13, tzinfo=UTC),
    )

    assert lesson.starts_at == datetime(2026, 9, 10, 12, tzinfo=UTC)
    assert lesson.ends_at == datetime(2026, 9, 10, 13, tzinfo=UTC)
    assert lesson.id == 501
    assert lesson.class_id == 10
    assert lesson.teacher_id == 100
    assert lesson.subject_id == 1000
    assert lesson.status == "planned"
    assert lesson.version == 3


def test_cancel_changes_status_and_rejects_second_cancellation() -> None:
    lesson = Lesson(
        id=501,
        class_id=10,
        teacher_id=100,
        subject_id=1000,
        starts_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
        ends_at=datetime(2026, 9, 10, 11, tzinfo=UTC),
        status="planned",
        version=3,
    )

    lesson.cancel()

    assert lesson.status == "canceled"
    assert lesson.id == 501
    assert lesson.version == 3

    with pytest.raises(LessonAlreadyCanceled):
        lesson.cancel()
