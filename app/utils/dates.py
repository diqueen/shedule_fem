"""Timezone-aware date helpers (Europe/Moscow by default)."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

MONTHS_NOMINATIVE_RU = [
    "",
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
]
MONTHS_GENITIVE_RU = [
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
]
WEEKDAYS_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]


def get_zone(tz_name: str) -> ZoneInfo:
    return ZoneInfo(tz_name)


def now_in(tz_name: str) -> datetime:
    return datetime.now(get_zone(tz_name))


def today_in(tz_name: str) -> date:
    return now_in(tz_name).date()


def tomorrow_in(tz_name: str) -> date:
    return today_in(tz_name) + timedelta(days=1)


def month_name_ru(month: int, *, genitive: bool = False) -> str:
    table = MONTHS_GENITIVE_RU if genitive else MONTHS_NOMINATIVE_RU
    return table[month]


def weekday_name_ru(day: date) -> str:
    return WEEKDAYS_RU[day.weekday()]


def format_date_ru(day: date, *, with_weekday: bool = True) -> str:
    base = f"{day.day} {month_name_ru(day.month, genitive=True)}"
    if with_weekday:
        return f"{weekday_name_ru(day)}, {base}"
    return base


def format_date_short(day: date) -> str:
    return f"{day.day:02d}.{day.month:02d}.{day.year}"


def format_datetime_msk(value: datetime | None, tz_name: str = "Europe/Moscow") -> str:
    if value is None:
        return "—"
    zone = get_zone(tz_name)
    if value.tzinfo is None:
        value = value.replace(tzinfo=zone)
    local = value.astimezone(zone)
    return local.strftime("%d.%m.%Y %H:%M MSK")


def week_bounds(day: date) -> tuple[date, date]:
    """Monday..Sunday of the week containing ``day``."""
    monday = day - timedelta(days=day.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)
    return start, end


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1
