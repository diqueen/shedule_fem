"""ScheduleService and date-logic tests."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.parser.exceptions import ScheduleSourceError
from app.parser.models import GroupRef
from app.services.cache_service import CacheService
from app.services.schedule_service import ScheduleService
from app.utils.dates import shift_month, tomorrow_in, week_bounds


class FakeClient:
    def __init__(self, catalog_html: str, month_html: str) -> None:
        self.catalog_html = catalog_html
        self.month_html = month_html
        self.error: Exception | None = None
        self.calls = 0
        self.groups_calls = 0
        self.bases = ["https://fake.test/raspisanie/"]

    async def get_catalog_html(self) -> str:
        return self.catalog_html

    async def get_groups(self, special, course):
        self.groups_calls += 1
        return [GroupRef(name="6511,6512", external_id="6511,6512")]

    async def get_months(self, special, course, group):
        return ["октябрь"]

    async def get_month_html(self, special, course, group, month) -> str:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.month_html

    async def close(self) -> None:  # pragma: no cover
        pass


def make_service(settings, db, client) -> ScheduleService:
    return ScheduleService(client, db, CacheService(settings.schedule_cache_ttl), settings)


# --------------------------------------------------------------------------- #
# Pure date logic
# --------------------------------------------------------------------------- #
def test_tomorrow_across_month_end():
    assert date(2026, 10, 31) + timedelta(days=1) == date(2026, 11, 1)


def test_tomorrow_across_year_end():
    assert date(2026, 12, 31) + timedelta(days=1) == date(2027, 1, 1)


def test_week_bounds_friday():
    monday, sunday = week_bounds(date(2026, 10, 2))
    assert monday == date(2026, 9, 28)
    assert sunday == date(2026, 10, 4)


def test_week_bounds_crosses_month():
    monday, sunday = week_bounds(date(2026, 11, 1))  # Sunday
    assert monday == date(2026, 10, 26)
    assert sunday == date(2026, 11, 1)


def test_shift_month_boundaries():
    assert shift_month(2026, 12, 1) == (2027, 1)
    assert shift_month(2027, 1, -1) == (2026, 12)
    assert shift_month(2026, 10, 0) == (2026, 10)


def test_tomorrow_in_uses_timezone():
    day = tomorrow_in("Europe/Moscow")
    assert isinstance(day, date)


# --------------------------------------------------------------------------- #
# ScheduleService
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_groups_and_cache(settings, db, main_page_html):
    client = FakeClient(main_page_html, "")
    service = make_service(settings, db, client)

    groups = await service.get_groups("Экономика", 2)
    assert [g.name for g in groups] == ["6511,6512"]
    assert client.groups_calls == 1

    # Cached call must not hit the website again.
    cached = await service.get_groups("Экономика", 2)
    assert [g.name for g in cached] == ["6511,6512"]
    assert client.groups_calls == 1

    # force=True must bypass the cache.
    forced = await service.get_groups("Экономика", 2, force=True)
    assert [g.name for g in forced] == ["6511,6512"]
    assert client.groups_calls == 2


@pytest.mark.asyncio
async def test_fetch_month_and_cache(settings, db, october_html, main_page_html):
    client = FakeClient(main_page_html, october_html)
    service = make_service(settings, db, client)

    result = await service.get_month("6511,6512", "Экономика", 2, 2026, 10)
    assert result.status == "ok"
    assert result.entries
    assert client.calls == 1

    # Second call is served from cache/db, no extra website request.
    cached = await service.get_month("6511,6512", "Экономика", 2, 2026, 10)
    assert cached.status == "ok"
    assert cached.entries
    assert client.calls == 1


@pytest.mark.asyncio
async def test_not_published_month(settings, db, main_page_html):
    empty = (
        '<table><caption>октябрь</caption>'
        '<tr class="lesson-line"><td>Дата</td><td id="day5">5 Октября</td></tr></table>'
    )
    client = FakeClient(main_page_html, empty)
    service = make_service(settings, db, client)
    result = await service.get_month("6511,6512", "Экономика", 2, 2026, 10)
    assert result.status == "not_published"
    assert result.entries == []


@pytest.mark.asyncio
async def test_source_error_keeps_last_known_good(settings, db, october_html, main_page_html):
    client = FakeClient(main_page_html, october_html)
    service = make_service(settings, db, client)

    first = await service.get_month("6511,6512", "Экономика", 2, 2026, 10)
    assert first.status == "ok"
    assert first.entries

    client.error = ScheduleSourceError("site down")
    stale = await service.get_month("6511,6512", "Экономика", 2, 2026, 10, force=True)
    assert stale.status == "stale"
    assert stale.entries  # old data preserved
    assert stale.error


@pytest.mark.asyncio
async def test_parser_break_does_not_wipe_data(settings, db, october_html, main_page_html):
    client = FakeClient(main_page_html, october_html)
    service = make_service(settings, db, client)
    await service.get_month("6511,6512", "Экономика", 2, 2026, 10)

    # Suddenly the site returns an empty (but valid) table.
    client.month_html = (
        '<table><caption>октябрь</caption>'
        '<tr class="lesson-line"><td>Дата</td><td id="day5">5 Октября</td></tr></table>'
    )
    result = await service.get_month("6511,6512", "Экономика", 2, 2026, 10, force=True)
    assert result.status == "stale"
    assert result.entries


@pytest.mark.asyncio
async def test_get_day_no_lessons(settings, db, october_html, main_page_html):
    client = FakeClient(main_page_html, october_html)
    service = make_service(settings, db, client)
    result = await service.get_day("6511,6512", "Экономика", 2, date(2026, 10, 3))
    assert result.status == "no_lessons"
    assert result.entries == []


@pytest.mark.asyncio
async def test_get_day_ok(settings, db, october_html, main_page_html):
    client = FakeClient(main_page_html, october_html)
    service = make_service(settings, db, client)
    result = await service.get_day("6511,6512", "Экономика", 2, date(2026, 10, 5))
    assert result.status == "ok"
    assert result.entries
    assert all(e.schedule_date == date(2026, 10, 5) for e in result.entries)


@pytest.mark.asyncio
async def test_get_day_error_without_cache(settings, db, main_page_html):
    client = FakeClient(main_page_html, "")
    client.error = ScheduleSourceError("site down")
    service = make_service(settings, db, client)
    result = await service.get_day("6511,6512", "Экономика", 2, date(2026, 10, 5))
    assert result.status == "error"
    assert result.entries == []


@pytest.mark.asyncio
async def test_get_week_returns_seven_days(settings, db, october_html, main_page_html):
    client = FakeClient(main_page_html, october_html)
    service = make_service(settings, db, client)
    results = await service.get_week("6511,6512", "Экономика", 2, date(2026, 10, 5))
    assert len(results) == 7
    assert results[0].day == date(2026, 10, 5)
    assert results[-1].day == date(2026, 10, 11)
