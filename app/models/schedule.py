from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Option:
    id: str
    name: str


@dataclass(frozen=True)
class Lesson:
    start_time: str
    end_time: str
    subject: str
    teacher: str | None = None
    classroom: str | None = None
    lesson_type: str | None = None
    groups: str | None = None


@dataclass
class DaySchedule:
    date: date
    lessons: list[Lesson] = field(default_factory=list)
