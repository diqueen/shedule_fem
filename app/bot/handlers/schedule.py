"""/schedule, /tomorrow, /week, /month."""
from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.container import Services
from app.database.models import ScheduleEntry, User
from app.services.schedule_service import DayResult, MonthResult
from app.utils.dates import (
    format_date_ru,
    month_name_ru,
    today_in,
    tomorrow_in,
    week_bounds,
)
from app.utils.formatting import (
    chunk_messages,
    format_day_schedule,
    format_no_lessons,
    format_not_published,
    format_source_error,
    format_stale_notice,
    format_week_day,
    format_week_header,
)

router = Router(name="schedule")

NO_PROFILE_MESSAGE = "Сначала выберите группу командой /start."


def render_day(group_name: str, day: date, result: DayResult) -> str:
    if result.status == "ok":
        message = format_day_schedule(group_name, day, result.entries)
        if result.stale or result.error:
            message = f"{message}\n\n{format_stale_notice()}"
        return message
    if result.status == "no_lessons":
        return format_no_lessons(group_name, day)
    if result.status == "not_published":
        return format_not_published(group_name, day)
    return format_source_error()


async def _load_profile(telegram_id: int, services: Services) -> User | None:
    return await services.users.get(telegram_id)


# --------------------------------------------------------------------------- #
# Core senders (work the same for a command or a menu button)
# --------------------------------------------------------------------------- #
async def send_nearest_day(target: Message, telegram_id: int, services: Services) -> None:
    profile = await _load_profile(telegram_id, services)
    if profile is None:
        await target.answer(NO_PROFILE_MESSAGE)
        return
    today = today_in(services.settings.timezone)
    result = await services.schedule.get_day(
        profile.group_id, profile.faculty, profile.course, today
    )
    if result.status == "ok" and result.entries:
        await target.answer(render_day(profile.group_name, today, result), parse_mode="HTML")
        return
    # Look ahead up to a week for the nearest day with lessons.
    for offset in range(1, 8):
        day = today + timedelta(days=offset)
        candidate = await services.schedule.get_day(
            profile.group_id, profile.faculty, profile.course, day
        )
        if candidate.status == "ok" and candidate.entries:
            await target.answer(
                render_day(profile.group_name, day, candidate), parse_mode="HTML"
            )
            return
    await target.answer(render_day(profile.group_name, today, result), parse_mode="HTML")


async def send_day(target: Message, telegram_id: int, services: Services, day: date) -> None:
    profile = await _load_profile(telegram_id, services)
    if profile is None:
        await target.answer(NO_PROFILE_MESSAGE)
        return
    result = await services.schedule.get_day(
        profile.group_id, profile.faculty, profile.course, day
    )
    await target.answer(render_day(profile.group_name, day, result), parse_mode="HTML")


async def send_week(target: Message, telegram_id: int, services: Services) -> None:
    profile = await _load_profile(telegram_id, services)
    if profile is None:
        await target.answer(NO_PROFILE_MESSAGE)
        return
    today = today_in(services.settings.timezone)
    monday, sunday = week_bounds(today)
    results = await services.schedule.get_week(
        profile.group_id, profile.faculty, profile.course, today
    )
    parts = [format_week_header(profile.group_name, monday, sunday), ""]
    for day_result in results:
        parts.append(_render_week_day(day_result))
        parts.append("")
    text = "\n".join(parts).strip()
    for chunk in chunk_messages(text):
        await target.answer(chunk, parse_mode="HTML")


async def send_month(target: Message, telegram_id: int, services: Services) -> None:
    profile = await _load_profile(telegram_id, services)
    if profile is None:
        await target.answer(NO_PROFILE_MESSAGE)
        return
    today = today_in(services.settings.timezone)
    result = await services.schedule.get_month_entries(
        profile.group_id, profile.faculty, profile.course, today.year, today.month
    )
    await _send_month(target, profile, result)


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
@router.message(Command("schedule"))
async def on_schedule(message: Message, services: Services) -> None:
    await send_nearest_day(message, message.from_user.id, services)


@router.message(Command("tomorrow"))
async def on_tomorrow(message: Message, services: Services) -> None:
    day = tomorrow_in(services.settings.timezone)
    await send_day(message, message.from_user.id, services, day)


@router.message(Command("week"))
async def on_week(message: Message, services: Services) -> None:
    await send_week(message, message.from_user.id, services)


def _render_week_day(result: DayResult) -> str:
    if result.status == "ok":
        return format_week_day(result.day, result.entries)
    if result.status == "no_lessons":
        return format_week_day(result.day, [])
    if result.status == "not_published":
        return f"<b>{format_date_ru(result.day)}</b>\n— нет данных"
    if result.status == "stale":
        return f"<b>{format_date_ru(result.day)}</b>\n— нет данных (источник недоступен)"
    return f"<b>{format_date_ru(result.day)}</b>\n— ошибка получения"


@router.message(Command("month"))
async def on_month(message: Message, services: Services) -> None:
    await send_month(message, message.from_user.id, services)


async def _send_month(message: Message, profile: User, result: MonthResult) -> None:
    if result.status == "error":
        await message.answer(format_source_error())
        return
    if result.status == "not_published" or not result.entries:
        await message.answer(
            f"📆 <b>{month_name_ru(result.month).capitalize()} {result.year}</b>\n\n"
            f"Расписание для группы {profile.group_name} пока не опубликовано."
        )
        return

    by_date: dict[date, list[ScheduleEntry]] = {}
    for entry in result.entries:
        by_date.setdefault(entry.schedule_date, []).append(entry)

    header = (
        f"📆 <b>{month_name_ru(result.month).capitalize()} {result.year}</b>\n"
        f"🎓 <b>Группа:</b> {profile.group_name}"
    )
    if result.status == "stale":
        header += f"\n{format_stale_notice()}"
    parts = [header, ""]
    for day in sorted(by_date):
        parts.append(format_week_day(day, by_date[day]))
        parts.append("")
    text = "\n".join(parts).strip()
    for chunk in chunk_messages(text):
        await message.answer(chunk, parse_mode="HTML")


# -- menu buttons ----------------------------------------------------------- #
# NB: use callback.from_user.id, never callback.message.from_user.id
# (in the latter, from_user is the bot itself, not the student).
@router.callback_query(F.data == "menu:tomorrow")
async def cb_tomorrow(callback: CallbackQuery, services: Services) -> None:
    await callback.answer()
    if callback.message is not None:
        day = tomorrow_in(services.settings.timezone)
        await send_day(callback.message, callback.from_user.id, services, day)


@router.callback_query(F.data == "menu:week")
async def cb_week(callback: CallbackQuery, services: Services) -> None:
    await callback.answer()
    if callback.message is not None:
        await send_week(callback.message, callback.from_user.id, services)


@router.callback_query(F.data == "menu:month")
async def cb_month(callback: CallbackQuery, services: Services) -> None:
    await callback.answer()
    if callback.message is not None:
        await send_month(callback.message, callback.from_user.id, services)
