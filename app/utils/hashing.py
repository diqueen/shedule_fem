"""Deterministic hashing used to detect schedule changes."""
from __future__ import annotations

import hashlib

from app.database.models import ScheduleEntry


def hash_entry(
    *,
    schedule_date: object,
    group_id: str,
    start_time: object,
    end_time: object,
    subject: str | None,
    teacher: str | None,
    classroom: str | None,
    lesson_type: str | None,
    note: str | None,
) -> str:
    payload = "|".join(
        [
            str(schedule_date),
            group_id,
            str(start_time),
            str(end_time),
            subject or "",
            teacher or "",
            classroom or "",
            lesson_type or "",
            note or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_entry_model(entry: ScheduleEntry) -> str:
    return hash_entry(
        schedule_date=entry.schedule_date,
        group_id=entry.group_id,
        start_time=entry.start_time,
        end_time=entry.end_time,
        subject=entry.subject,
        teacher=entry.teacher,
        classroom=entry.classroom,
        lesson_type=entry.lesson_type,
        note=entry.note,
    )


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
