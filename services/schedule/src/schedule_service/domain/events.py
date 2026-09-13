from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LessonCreated:
    lesson_id: int
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime
    status: str
    version: int
