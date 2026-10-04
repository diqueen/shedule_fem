"""HTML message formatting for Telegram."""
from __future__ import annotations

from datetime import date, time
from html import escape

from app.database.models import ScheduleEntry
from app.utils.dates import format_date_ru, weekday_name_ru

_DIGITS = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

LESSON_TYPE_TITLES = {
    "лекция": "Лекция",
    "практика": "Практика",
    "семинар": "Семинар",
    "лабораторная": "Лабораторная",
    "курсовая работа": "Курсовая работа",
    "консультация": "Консультация",
    "зачёт": "Зачёт",
    "экзамен": "Экзамен",
}

TELEGRAM_LIMIT = 4000


def _num(index: int) -> str:
    return _DIGITS[index] if 0 <= index < len(_DIGITS) else f"{index}."


def _fmt_time(value: time | None) -> str:
    return value.strftime("%H:%M") if value else ""


def format_time_range(start: time | None, end: time | None) -> str:
    if start and end:
        return f"{_fmt_time(start)}–{_fmt_time(end)}"
    if start:
        return _fmt_time(start)
    return ""


def format_day_header(day: date) -> str:
    return f"📅 <b>{escape(format_date_ru(day))}</b>"


def format_group_line(group_name: str) -> str:
    return f"🎓 <b>Группа:</b> {escape(group_name)}"


def format_lesson(entry: ScheduleEntry, index: int) -> str:
    lines: list[str] = []
    time_range = format_time_range(entry.start_time, entry.end_time)
    head = f"{_num(index)}"
    if time_range:
        head += f" <b>{escape(time_range)}</b>"
    lines.append(head)
    if entry.subject:
        lines.append(f"📚 {escape(entry.subject)}")
    if entry.lesson_type:
        title = LESSON_TYPE_TITLES.get(entry.lesson_type, entry.lesson_type)
        lines.append(f"🎓 {escape(title)}")
    if entry.teacher:
        lines.append(f"👨‍🏫 {escape(entry.teacher)}")
    if entry.classroom:
        lines.append(f"🏫 {escape(entry.classroom)}")
    if entry.note:
        lines.append(f"ℹ️ {escape(entry.note)}")
    return "\n".join(lines)


def format_day_schedule(group_name: str, day: date, entries: list[ScheduleEntry]) -> str:
    parts = [format_day_header(day), format_group_line(group_name), ""]
    for index, entry in enumerate(entries, start=1):
        parts.append(format_lesson(entry, index))
        parts.append("")
    return "\n".join(parts).strip()


def format_no_lessons(group_name: str, day: date) -> str:
    return (
        f"{format_day_header(day)}\n"
        f"{format_group_line(group_name)}\n\n"
        "Занятий нет."
    )


def format_not_published(group_name: str, day: date) -> str:
    return (
        f"{format_day_header(day)}\n\n"
        f"Расписание для группы {escape(group_name)} пока не найдено.\n\n"
        "Возможно:\n"
        "• расписание ещё не опубликовано;\n"
        "• занятий действительно нет;\n"
        "• источник временно недоступен."
    )


def format_source_error() -> str:
    return (
        "⚠️ Не удалось получить актуальное расписание.\n\n"
        "Источник расписания временно недоступен. Попробуйте повторить запрос позже."
    )


def format_tomorrow_source_error() -> str:
    return (
        "⚠️ Не удалось проверить расписание на завтра.\n\n"
        "Источник расписания временно недоступен."
    )


def format_stale_notice() -> str:
    return "ℹ️ Используются последние доступные данные расписания."


def format_no_schedule_selected() -> str:
    return "Сначала выберите группу командой /start."


def chunk_messages(text: str, limit: int = TELEGRAM_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.split("\n"):
        line_len = len(line) + 1
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len
    if current:
        chunks.append("\n".join(current))
    return chunks


def format_week_header(group_name: str, start: date, end: date) -> str:
    return (
        f"🗓 <b>Неделя {start.day:02d}.{start.month:02d} – "
        f"{end.day:02d}.{end.month:02d}</b>\n"
        f"🎓 <b>Группа:</b> {escape(group_name)}"
    )


def format_week_day(day: date, entries: list[ScheduleEntry]) -> str:
    header = f"<b>{escape(weekday_name_ru(day))}, {day.day} {_month_genitive(day.month)}</b>"
    if not entries:
        return f"{header}\n— занятий нет"
    lines = [header]
    for index, entry in enumerate(entries, start=1):
        time_range = format_time_range(entry.start_time, entry.end_time)
        subject = escape(entry.subject or entry.subject_raw)
        suffix = f" — {escape(entry.classroom)}" if entry.classroom else ""
        lines.append(f"{_num(index)} {escape(time_range)} {subject}{suffix}")
    return "\n".join(lines)


def _month_genitive(month: int) -> str:
    from app.utils.dates import month_name_ru

    return month_name_ru(month, genitive=True)
