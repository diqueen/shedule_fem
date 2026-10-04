"""Broadcast tests with a fake Telegram bot and a fake schedule service."""
from __future__ import annotations

from datetime import date, time

import pytest
from aiogram.exceptions import TelegramForbiddenError

from app.database.models import ScheduleEntry
from app.database.repositories import NotificationLogRepository
from app.services.notification_service import NotificationService, build_day_message
from app.services.schedule_service import DayResult
from app.services.user_service import UserService

DAY = date(2026, 10, 6)


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str]] = []
        self.error: Exception | None = None
        self.error_for: int | None = None

    async def send_message(self, chat_id: int, text: str, parse_mode: str | None = None):
        if self.error is not None and (self.error_for is None or self.error_for == chat_id):
            raise self.error
        self.messages.append((chat_id, text))
        return None


class FakeSchedule:
    def __init__(self, result: DayResult) -> None:
        self.result = result
        self.calls = 0

    async def get_day(self, group_id, special, course, day, *, force: bool = False) -> DayResult:
        self.calls += 1
        return self.result


def make_entry(group_id: str, day: date = DAY) -> ScheduleEntry:
    return ScheduleEntry(
        schedule_date=day,
        group_id=group_id,
        source_id="865118",
        lesson_number=1,
        start_time=time(9, 30),
        end_time=time(11, 10),
        subject="Менеджмент",
        subject_raw="Менеджмент (пр)",
        teacher="Сидорова Н. А.",
        classroom="а.6373",
        lesson_type="практика",
        source_number="(18)11",
        note=None,
        raw_text="Менеджмент (пр) а.6373 Сидорова Н. А.",
        source_hash="deadbeef",
    )


async def _add_user(service: UserService, telegram_id: int, group: str = "6511,6512"):
    return await service.register(
        telegram_id=telegram_id,
        username=None,
        education_level="Бакалавриат",
        faculty="Экономика",
        course=2,
        group_id=group,
        group_name=group,
    )


def make_service(settings, db, bot, result: DayResult) -> tuple[NotificationService, FakeSchedule]:
    schedule = FakeSchedule(result)
    service = NotificationService(bot, db, schedule, settings)
    return service, schedule


@pytest.mark.asyncio
async def test_successful_send(settings, db):
    users = UserService(db)
    await _add_user(users, 1)
    bot = FakeBot()
    result = DayResult(DAY, [make_entry("6511,6512")], "ok")
    service, schedule = make_service(settings, db, bot, result)

    report = await service.send_tomorrow(day=DAY)
    assert report.sent == 1
    assert report.failed == 0
    assert len(bot.messages) == 1
    assert "Менеджмент" in bot.messages[0][1]
    assert schedule.calls == 1  # queried once per group

    async with db.session() as session:
        log = await NotificationLogRepository(session).get(1, DAY)
    assert log is not None and log.status == "sent"


@pytest.mark.asyncio
async def test_duplicate_send_is_skipped(settings, db):
    users = UserService(db)
    await _add_user(users, 1)
    bot = FakeBot()
    result = DayResult(DAY, [make_entry("6511,6512")], "ok")
    service, _ = make_service(settings, db, bot, result)

    first = await service.send_tomorrow(day=DAY)
    second = await service.send_tomorrow(day=DAY)
    assert first.sent == 1
    assert second.sent == 0
    assert second.skipped == 1
    assert len(bot.messages) == 1


@pytest.mark.asyncio
async def test_blocked_user_disables_notifications(settings, db):
    users = UserService(db)
    await _add_user(users, 1)
    bot = FakeBot()
    bot.error = TelegramForbiddenError(None, "bot was blocked by the user")
    result = DayResult(DAY, [make_entry("6511,6512")], "ok")
    service, _ = make_service(settings, db, bot, result)

    report = await service.send_tomorrow(day=DAY)
    assert report.blocked == 1
    assert report.sent == 0

    profile = await users.get(1)
    assert profile is not None and profile.notifications_enabled is False

    async with db.session() as session:
        log = await NotificationLogRepository(session).get(1, DAY)
    assert log is not None and log.status == "blocked"


@pytest.mark.asyncio
async def test_telegram_error_is_isolated_per_user(settings, db):
    users = UserService(db)
    await _add_user(users, 1)
    await _add_user(users, 2)
    bot = FakeBot()
    bot.error = RuntimeError("temporary telegram failure")
    bot.error_for = 1  # only the first user fails
    result = DayResult(DAY, [make_entry("6511,6512")], "ok")
    service, _ = make_service(settings, db, bot, result)

    report = await service.send_tomorrow(day=DAY)
    assert report.failed == 1
    assert report.sent == 1
    assert {chat_id for chat_id, _ in bot.messages} == {2}

    async with db.session() as session:
        failed_log = await NotificationLogRepository(session).get(1, DAY)
        sent_log = await NotificationLogRepository(session).get(2, DAY)
    assert failed_log is not None and failed_log.status == "error"
    assert sent_log is not None and sent_log.status == "sent"


@pytest.mark.asyncio
async def test_notification_respects_disabled_users(settings, db):
    users = UserService(db)
    await _add_user(users, 1)
    await users.set_notifications(1, False)
    bot = FakeBot()
    result = DayResult(DAY, [make_entry("6511,6512")], "ok")
    service, schedule = make_service(settings, db, bot, result)

    report = await service.send_tomorrow(day=DAY)
    assert report.total == 0
    assert schedule.calls == 0
    assert bot.messages == []


# --------------------------------------------------------------------------- #
# Message rendering
# --------------------------------------------------------------------------- #
def test_build_message_no_lessons():
    text = build_day_message("6511,6512", DAY, DayResult(DAY, [], "no_lessons"))
    assert "Занятий нет" in text


def test_build_message_not_published():
    text = build_day_message("6511,6512", DAY, DayResult(DAY, [], "not_published"))
    assert "не найдено" in text


def test_build_message_error():
    text = build_day_message("6511,6512", DAY, DayResult(DAY, [], "error"))
    assert "недоступен" in text


def test_build_message_stale_with_data_mentions_last_data():
    result = DayResult(DAY, [make_entry("6511,6512")], "ok", from_cache=True, error="down")
    text = build_day_message("6511,6512", DAY, result)
    assert "последние доступные данные" in text


def test_build_message_ok_lists_lesson():
    result = DayResult(DAY, [make_entry("6511,6512")], "ok")
    text = build_day_message("6511,6512", DAY, result)
    assert "Менеджмент" in text
    assert "Сидорова Н. А." in text
    assert "а.6373" in text
