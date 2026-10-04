"""ScheduleService: parser + cache + database orchestration.

This is the only place where a website request turns into stored, normalized
schedule data. Telegram handlers never parse HTML and never call the client
directly.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone

from app.config import Settings
from app.database.database import Database
from app.database.models import ScheduleEntry
from app.database.repositories import (
    GroupRepository,
    ScheduleFetchLogRepository,
    ScheduleRepository,
)
from app.parser.client import ScheduleClient
from app.parser.exceptions import ScheduleError, ScheduleSourceError, ScheduleStructureError
from app.parser.models import Catalog, GroupRef, LessonData
from app.parser.parser import parse_catalog, parse_month_html
from app.services.cache_service import CacheService
from app.utils.dates import (
    month_name_ru,
    today_in,
    week_bounds,
)
from app.utils.hashing import hash_entry, hash_text

logger = logging.getLogger(__name__)

CATALOG_TTL = 6 * 3600
GROUPS_TTL = 6 * 3600


@dataclass(slots=True)
class MonthResult:
    group_id: str
    year: int
    month: int
    entries: list[ScheduleEntry] = field(default_factory=list)
    status: str = "ok"  # ok | stale | not_published | error
    from_cache: bool = False
    error: str | None = None
    fetched_at: datetime | None = None


@dataclass(slots=True)
class DayResult:
    day: date
    entries: list[ScheduleEntry] = field(default_factory=list)
    status: str = "ok"  # ok | no_lessons | not_published | stale | error
    from_cache: bool = False
    error: str | None = None

    @property
    def stale(self) -> bool:
        return self.status == "stale"


@dataclass(slots=True)
class RefreshReport:
    year: int
    month: int
    groups: int = 0
    entries: int = 0
    errors: list[str] = field(default_factory=list)
    duration: float = 0.0
    status: str = "ok"


class ScheduleService:
    def __init__(
        self,
        client: ScheduleClient,
        db: Database,
        cache: CacheService,
        settings: Settings,
    ) -> None:
        self.client = client
        self.db = db
        self.cache = cache
        self.settings = settings

    # ------------------------------------------------------------------ #
    # Catalog / groups / months
    # ------------------------------------------------------------------ #
    async def get_catalog(self, *, force: bool = False) -> Catalog:
        key = self.cache.catalog_key()
        if not force:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        html = await self.client.get_catalog_html()
        catalog = parse_catalog(html)
        self.cache.set(key, catalog, CATALOG_TTL)
        return catalog

    async def get_groups(
        self, special: str, course: int, *, force: bool = False
    ) -> list[GroupRef]:
        key = f"groups:{special}:{course}"
        if not force:
            cached = self.cache.get(key)
            if cached is not None:
                return cached
        groups = await self.client.get_groups(special, course)
        self.cache.set(key, groups, GROUPS_TTL)
        return groups

    async def get_available_months(self, special: str, course: int, group_id: str) -> list[str]:
        return await self.client.get_months(special, course, group_id)

    # ------------------------------------------------------------------ #
    # Month
    # ------------------------------------------------------------------ #
    async def get_month(
        self,
        group_id: str,
        special: str,
        course: int,
        year: int,
        month: int,
        *,
        force: bool = False,
    ) -> MonthResult:
        key = self.cache.month_key(year, month, group_id)
        scope = key
        reference = today_in(self.settings.timezone)

        if not force and self.cache.is_fresh(key):
            async with self.db.session() as session:
                entries = await ScheduleRepository(session).get_for_month(group_id, year, month)
            if entries:
                return MonthResult(group_id, year, month, entries, "ok", from_cache=True)

        async with self.db.session() as session:
            log = await ScheduleFetchLogRepository(session).get(scope)
            fresh = (
                log is not None
                and log.status == "ok"
                and log.fetched_at is not None
                and _age_seconds(log.fetched_at) < self.settings.schedule_cache_ttl
                and log.entries_count > 0
            )
            if not force and fresh:
                entries = await ScheduleRepository(session).get_for_month(group_id, year, month)
                if entries:
                    self.cache.set(key, True, self.settings.schedule_cache_ttl)
                    return MonthResult(group_id, year, month, entries, "ok", from_cache=True)
            previous_count = log.entries_count if log else 0

        month_name = month_name_ru(month)
        try:
            html = await self.client.get_month_html(special, course, group_id, month_name)
            parsed = parse_month_html(html, reference)
            self._sanity_check(parsed, previous_count, group_id, year, month)

            models = self._build_models(parsed.entries, group_id)
            async with self.db.session() as session:
                await ScheduleRepository(session).replace_month(group_id, year, month, models)
                await ScheduleFetchLogRepository(session).set_result(
                    scope_key=scope,
                    year=year,
                    month=month,
                    group_id=group_id,
                    status="ok",
                    entries_count=len(models),
                    source_url=self.client.bases[0] if self.client.bases else None,
                    source_hash=hash_text(html),
                )
            self.cache.set(key, True, self.settings.schedule_cache_ttl)
            entries = models
            status = "ok" if entries else "not_published"
            logger.info(
                "Schedule fetch completed group=%s month=%04d-%02d entries=%s",
                group_id, year, month, len(entries),
            )
            return MonthResult(group_id, year, month, entries, status, from_cache=False)
        except ScheduleError as exc:
            logger.warning(
                "Schedule fetch failed group=%s month=%04d-%02d: %s",
                group_id, year, month, exc,
            )
            await self._record_error(scope, group_id, year, month, str(exc), previous_count)
            async with self.db.session() as session:
                entries = await ScheduleRepository(session).get_for_month(group_id, year, month)
            if entries:
                return MonthResult(
                    group_id, year, month, entries, "stale", from_cache=True, error=str(exc)
                )
            return MonthResult(group_id, year, month, [], "error", error=str(exc))

    def _sanity_check(
        self,
        parsed,
        previous_count: int,
        group_id: str,
        year: int,
        month: int,
    ) -> None:
        if parsed.entries and not any(e.start_time for e in parsed.entries):
            raise ScheduleStructureError("No time ranges parsed from month table")
        if not parsed.entries and previous_count > 0:
            raise ScheduleStructureError(
                f"Parser returned 0 entries while {previous_count} were stored before"
            )
        if parsed.entries and not any(e.schedule_date for e in parsed.entries):
            raise ScheduleStructureError("Parsed entries have no dates")
        if parsed.entries and not any(e.group_id for e in parsed.entries):
            raise ScheduleStructureError("Parsed entries have no group ids")
        logger.debug(
            "Sanity ok group=%s month=%04d-%02d entries=%s days=%s groups=%s",
            group_id, year, month, len(parsed.entries), len(parsed.days), len(parsed.groups),
        )

    def _build_models(self, lessons: list[LessonData], fallback_group: str) -> list[ScheduleEntry]:
        by_date: dict[date, list[LessonData]] = {}
        for lesson in lessons:
            by_date.setdefault(lesson.schedule_date, []).append(lesson)

        models: list[ScheduleEntry] = []
        for day, day_lessons in by_date.items():
            day_lessons.sort(key=lambda x: (x.start_time or time(23, 59, 59), x.source_id))
            for number, lesson in enumerate(day_lessons, start=1):
                group_id = lesson.group_id or fallback_group
                models.append(
                    ScheduleEntry(
                        schedule_date=lesson.schedule_date,
                        group_id=group_id,
                        source_id=lesson.source_id,
                        lesson_number=number,
                        start_time=lesson.start_time,
                        end_time=lesson.end_time,
                        subject=lesson.subject,
                        subject_raw=lesson.subject_raw,
                        teacher=lesson.teacher,
                        classroom=lesson.classroom,
                        lesson_type=lesson.lesson_type,
                        source_number=lesson.source_number,
                        note=lesson.note,
                        raw_text=lesson.raw_text,
                        source_hash=hash_entry(
                            schedule_date=lesson.schedule_date,
                            group_id=group_id,
                            start_time=lesson.start_time,
                            end_time=lesson.end_time,
                            subject=lesson.subject,
                            teacher=lesson.teacher,
                            classroom=lesson.classroom,
                            lesson_type=lesson.lesson_type,
                            note=lesson.note,
                        ),
                    )
                )
        return models

    async def _record_error(
        self,
        scope: str,
        group_id: str,
        year: int,
        month: int,
        error: str,
        previous_count: int,
    ) -> None:
        async with self.db.session() as session:
            await ScheduleFetchLogRepository(session).set_result(
                scope_key=scope,
                year=year,
                month=month,
                group_id=group_id,
                status="error",
                entries_count=previous_count,
                source_url=self.client.bases[0] if self.client.bases else None,
                source_hash=None,
                error=error,
            )

    # ------------------------------------------------------------------ #
    # Day / week / month views
    # ------------------------------------------------------------------ #
    async def get_day(
        self,
        group_id: str,
        special: str,
        course: int,
        day: date,
        *,
        force: bool = False,
    ) -> DayResult:
        month_result = await self.get_month(
            group_id, special, course, day.year, day.month, force=force
        )
        entries = [e for e in month_result.entries if e.schedule_date == day]
        if month_result.status == "error":
            return DayResult(day, [], "error", error=month_result.error)
        if month_result.status == "stale":
            if entries:
                return DayResult(day, entries, "ok", from_cache=True, error=month_result.error)
            return DayResult(day, [], "stale", from_cache=True, error=month_result.error)
        if month_result.status == "not_published":
            return DayResult(day, [], "not_published", from_cache=month_result.from_cache)
        if entries:
            return DayResult(day, entries, "ok", from_cache=month_result.from_cache)
        return DayResult(day, [], "no_lessons", from_cache=month_result.from_cache)

    async def get_week(
        self,
        group_id: str,
        special: str,
        course: int,
        reference: date,
        *,
        force: bool = False,
    ) -> list[DayResult]:
        monday, sunday = week_bounds(reference)
        months: set[tuple[int, int]] = {(monday.year, monday.month), (sunday.year, sunday.month)}
        collected: list[ScheduleEntry] = []
        statuses: dict[tuple[int, int], str] = {}
        errors: dict[tuple[int, int], str | None] = {}
        for year, month in months:
            result = await self.get_month(group_id, special, course, year, month, force=force)
            statuses[(year, month)] = result.status
            errors[(year, month)] = result.error
            collected.extend(result.entries)

        results: list[DayResult] = []
        for offset in range(7):
            day = monday.fromordinal(monday.toordinal() + offset)
            key = (day.year, day.month)
            entries = [e for e in collected if e.schedule_date == day]
            status = statuses.get(key, "error")
            if status == "error":
                results.append(DayResult(day, [], "error", error=errors.get(key)))
            elif status == "stale":
                if entries:
                    results.append(DayResult(day, entries, "ok", from_cache=True))
                else:
                    results.append(DayResult(day, [], "stale", from_cache=True, error=errors.get(key)))
            elif status == "not_published":
                results.append(DayResult(day, [], "not_published"))
            elif entries:
                results.append(DayResult(day, entries, "ok"))
            else:
                results.append(DayResult(day, [], "no_lessons"))
        return results

    async def get_month_entries(
        self,
        group_id: str,
        special: str,
        course: int,
        year: int,
        month: int,
        *,
        force: bool = False,
    ) -> MonthResult:
        return await self.get_month(group_id, special, course, year, month, force=force)

    # ------------------------------------------------------------------ #
    # Refresh (scheduler / admin)
    # ------------------------------------------------------------------ #
    async def refresh_month(self, year: int, month: int, *, catalog: Catalog | None = None) -> RefreshReport:
        started = time.monotonic()
        report = RefreshReport(year=year, month=month)
        catalog = catalog or await self.get_catalog()
        seen_groups: set[tuple[str, int, str]] = set()

        for speciality in catalog.specialities:
            for course in catalog.courses_for(speciality.id):
                try:
                    groups = await self.get_groups(speciality.name, course.number)
                except ScheduleError as exc:
                    report.errors.append(f"{speciality.name} {course.number}: {exc}")
                    continue
                for group in groups:
                    identity = (speciality.name, course.number, group.name)
                    if identity in seen_groups:
                        continue
                    seen_groups.add(identity)
                    report.groups += 1
                    result = await self.get_month(
                        group.name, speciality.name, course.number, year, month, force=True
                    )
                    if result.status in ("ok", "not_published"):
                        report.entries += len(result.entries)
                    else:
                        report.errors.append(f"{group.name}: {result.error or result.status}")

        report.duration = time.monotonic() - started
        report.status = "ok" if not report.errors else "partial"
        logger.info(
            "Month refresh finished %04d-%02d groups=%s entries=%s errors=%s duration=%.1fs",
            year, month, report.groups, report.entries, len(report.errors), report.duration,
        )
        return report


def _age_seconds(fetched_at: datetime) -> float:
    """Seconds elapsed since ``fetched_at`` (naive values are treated as UTC)."""
    if fetched_at.tzinfo is None:
        fetched_at = fetched_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - fetched_at).total_seconds()
