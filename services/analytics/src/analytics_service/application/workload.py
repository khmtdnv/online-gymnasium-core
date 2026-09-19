from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class ClassDailyWorkload:
    class_id: int
    day: date
    planned_lessons_count: int
    planned_minutes: int
    refreshed_at: datetime
