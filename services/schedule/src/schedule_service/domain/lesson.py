from dataclasses import dataclass
from datetime import datetime


class DomainException(Exception):
    pass


class InvalidLessonInterval(DomainException):
    pass


class LessonAlreadyCanceled(DomainException):
    pass


@dataclass
class Lesson:
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime
    id: int | None = None
    status: str = "planned"
    version: int = 1

    @staticmethod
    def create(
        class_id: int,
        teacher_id: int,
        subject_id: int,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Lesson:
        if starts_at >= ends_at:
            raise InvalidLessonInterval

        return Lesson(
            class_id=class_id,
            teacher_id=teacher_id,
            subject_id=subject_id,
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def reschedule(self, starts_at: datetime, ends_at: datetime) -> None:
        if starts_at >= ends_at:
            raise InvalidLessonInterval

        self.starts_at = starts_at
        self.ends_at = ends_at

    def cancel(self) -> None:
        if self.status == "canceled":
            raise LessonAlreadyCanceled

        self.status = "canceled"
