from datetime import UTC, datetime

import pytest

from schedule_service.domain.lesson import InvalidLessonInterval, Lesson


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
