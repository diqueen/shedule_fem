"""Domain models returned by the parser (source-agnostic shape)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time


@dataclass(slots=True, frozen=True)
class EducationLevel:
    id: str
    name: str


@dataclass(slots=True, frozen=True)
class Speciality:
    id: str
    name: str
    education_id: str


@dataclass(slots=True, frozen=True)
class Course:
    special_id: str
    number: int
    name: str


@dataclass(slots=True, frozen=True)
class GroupRef:
    """A selectable group.

    ``name`` is what the website shows and what must be sent back as the
    ``group`` POST parameter. ``external_id`` is the ``data-group`` value used
    inside the timetable table (on this site it equals ``name``).
    """

    name: str
    external_id: str


@dataclass(slots=True)
class Catalog:
    education_levels: list[EducationLevel] = field(default_factory=list)
    specialities: list[Speciality] = field(default_factory=list)
    courses: list[Course] = field(default_factory=list)

    def specialities_for(self, education_id: str) -> list[Speciality]:
        return [s for s in self.specialities if s.education_id == education_id]

    def courses_for(self, special_id: str) -> list[Course]:
        seen: set[int] = set()
        result: list[Course] = []
        for c in sorted(self.courses, key=lambda c: c.number):
            if c.special_id == special_id and c.number not in seen:
                seen.add(c.number)
                result.append(c)
        return result


@dataclass(slots=True)
class LessonData:
    """Normalized single lesson extracted from a ``<td>``."""

    source_id: str
    group_id: str
    schedule_date: date
    start_time: time | None
    end_time: time | None
    subject: str | None
    subject_raw: str
    teacher: str | None
    classroom: str | None
    lesson_type: str | None
    source_number: str | None
    note: str | None
    raw_text: str


@dataclass(slots=True)
class MonthParseResult:
    entries: list[LessonData]
    days: set[int] = field(default_factory=set)
    groups: set[str] = field(default_factory=set)
    raw_cells: int = 0
