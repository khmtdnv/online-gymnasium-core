from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class LessonSnapshot:
    event_id: int
    occurred_at: datetime
    lesson_id: int
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime
    status: str
    version: int


def parse_lesson_snapshot(envelope: dict[str, object]) -> LessonSnapshot | None:
    if envelope["event_type"] != "lesson.snapshot":
        return None

    payload = envelope["payload"]

    if not isinstance(payload, dict):
        raise TypeError("payload must be an object")

    try:
        return LessonSnapshot(
            event_id=envelope["event_id"],
            occurred_at=datetime.fromisoformat(envelope["occurred_at"]),
            lesson_id=payload["lesson_id"],
            class_id=payload["class_id"],
            teacher_id=payload["teacher_id"],
            subject_id=payload["subject_id"],
            starts_at=datetime.fromisoformat(payload["starts_at"]),
            ends_at=datetime.fromisoformat(payload["ends_at"]),
            status=payload["status"],
            version=payload["version"],
        )
    except KeyError as exc:
        raise ValueError(f"Missing required field: {exc.args[0]}") from exc
