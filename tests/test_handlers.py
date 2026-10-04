"""Regression tests for menu-button handlers.

A menu button arrives as a CallbackQuery whose ``message.from_user`` is the
*robot*, not the student. Handlers must therefore read ``callback.from_user.id``.
This was a real bug: pressing "Расписание на завтра" answered
"Сначала выберите группу командой /start." even for a registered user.
"""
from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from app.bot.handlers import schedule as schedule_handlers
from app.services.schedule_service import DayResult

STUDENT_ID = 1068849461
BOT_ID = 8929501806


class FakeMessage:
    def __init__(self, from_user_id: int) -> None:
        self.from_user = SimpleNamespace(id=from_user_id)
        self.sent: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.sent.append(text)


class FakeCallback:
    def __init__(self, from_user_id: int, message: FakeMessage) -> None:
        self.from_user = SimpleNamespace(id=from_user_id)
        self.message = message
        self.answered = False

    async def answer(self, *args, **kwargs) -> None:
        self.answered = True


class FakeUserService:
    def __init__(self, profile) -> None:
        self.profile = profile
        self.lookups: list[int] = []

    async def get(self, telegram_id: int):
        self.lookups.append(telegram_id)
        if self.profile is not None and telegram_id == self.profile.telegram_id:
            return self.profile
        return None


class FakeScheduleService:
    async def get_day(self, group_id, special, course, day, *, force: bool = False) -> DayResult:
        return DayResult(day, [], "no_lessons")

    async def get_week(self, group_id, special, course, reference, *, force: bool = False):
        from datetime import timedelta

        monday = reference - timedelta(days=reference.weekday())
        return [DayResult(monday + timedelta(days=i), [], "no_lessons") for i in range(7)]


def make_services(profile) -> SimpleNamespace:
    return SimpleNamespace(
        settings=SimpleNamespace(timezone="Europe/Moscow"),
        users=FakeUserService(profile),
        schedule=FakeScheduleService(),
    )


def make_profile(telegram_id: int = STUDENT_ID):
    return SimpleNamespace(
        telegram_id=telegram_id,
        group_id="6541,6542",
        group_name="6541,6542",
        faculty="Маркетинг",
        course=2,
        notifications_enabled=True,
    )


@pytest.mark.asyncio
async def test_menu_button_uses_callback_user_id():
    services = make_services(make_profile())
    # The message was sent by the bot, so message.from_user is the bot.
    bot_message = FakeMessage(BOT_ID)
    callback = FakeCallback(STUDENT_ID, bot_message)

    await schedule_handlers.cb_tomorrow(callback, services)

    assert callback.answered
    assert services.users.lookups == [STUDENT_ID]
    assert bot_message.sent, "handler must send a reply"
    assert "Сначала выберите группу" not in bot_message.sent[0]


@pytest.mark.asyncio
async def test_menu_button_without_profile_asks_to_start():
    services = make_services(profile=None)
    bot_message = FakeMessage(BOT_ID)
    callback = FakeCallback(STUDENT_ID, bot_message)

    await schedule_handlers.cb_tomorrow(callback, services)

    assert bot_message.sent[0] == schedule_handlers.NO_PROFILE_MESSAGE


@pytest.mark.asyncio
async def test_week_button_uses_callback_user_id():
    services = make_services(make_profile())
    bot_message = FakeMessage(BOT_ID)
    callback = FakeCallback(STUDENT_ID, bot_message)

    await schedule_handlers.cb_week(callback, services)

    assert services.users.lookups == [STUDENT_ID]
    assert "Сначала выберите группу" not in "\n".join(bot_message.sent)


@pytest.mark.asyncio
async def test_month_button_uses_callback_user_id():
    services = make_services(make_profile())

    async def get_month_entries(group_id, special, course, year, month, *, force=False):
        from app.services.schedule_service import MonthResult

        return MonthResult(group_id, year, month, [], "not_published")

    services.schedule.get_month_entries = get_month_entries
    bot_message = FakeMessage(BOT_ID)
    callback = FakeCallback(STUDENT_ID, bot_message)

    await schedule_handlers.cb_month(callback, services)

    assert services.users.lookups == [STUDENT_ID]
    assert "Сначала выберите группу" not in "\n".join(bot_message.sent)
