"""Inline keyboard builders.

Callback payloads carry stable identifiers (site ids / course numbers / list
indexes) instead of free text, so a user can never inject an arbitrary group.
"""
from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.parser.models import Course, EducationLevel, GroupRef, Speciality

PAGE_SIZE = 8


def _paginate(items: Sequence, page: int) -> tuple[Sequence, int, bool, bool]:
    total_pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PAGE_SIZE
    return items[start:start + PAGE_SIZE], total_pages, page > 0, page < total_pages - 1


def main_menu_kb(has_profile: bool, is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if not has_profile:
        builder.button(text="Начать регистрацию", callback_data="reg:start")
    else:
        builder.button(text="📅 Расписание на завтра", callback_data="menu:tomorrow")
        builder.button(text="🗓 Неделя", callback_data="menu:week")
        builder.button(text="📆 Месяц", callback_data="menu:month")
        builder.button(text="⚙️ Настройки", callback_data="set:menu")
    builder.button(text="❓ Помощь", callback_data="menu:help")
    if is_admin:
        builder.button(text="📊 Статистика", callback_data="menu:stats")
        builder.button(text="🔄 Обновить кэш", callback_data="menu:refresh")
    builder.adjust(1)
    return builder.as_markup()


def education_kb(
    levels: Sequence[EducationLevel], prefix: str = "reg"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for level in levels:
        builder.button(text=level.name, callback_data=f"{prefix}:edu:{level.id}")
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(1)
    return builder.as_markup()


def faculty_kb(
    specials: Sequence[Speciality], page: int = 0, prefix: str = "reg"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    page_items, total_pages, has_prev, has_next = _paginate(specials, page)
    for special in page_items:
        builder.button(text=special.name, callback_data=f"{prefix}:spec:{special.id}")
    _add_pagination(builder, prefix, "fac", page, total_pages, has_prev, has_next)
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(1)
    return builder.as_markup()


def course_kb(courses: Sequence[Course], prefix: str = "reg") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for course in courses:
        builder.button(text=course.name, callback_data=f"{prefix}:course:{course.number}")
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(1)
    return builder.as_markup()


def group_kb(
    groups: Sequence[GroupRef], page: int = 0, prefix: str = "reg"
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    page_items, total_pages, has_prev, has_next = _paginate(groups, page)
    for index, group in enumerate(page_items):
        absolute_index = page * PAGE_SIZE + index
        builder.button(text=group.name, callback_data=f"{prefix}:group:{page}:{absolute_index}")
    _add_pagination(builder, prefix, "groups", page, total_pages, has_prev, has_next)
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(1)
    return builder.as_markup()


def _add_pagination(builder, prefix, kind, page, total_pages, has_prev, has_next) -> None:
    if total_pages <= 1:
        return
    if has_prev:
        builder.button(text="⬅️", callback_data=f"{prefix}:{kind}:{page - 1}")
    builder.button(text=f"{page + 1}/{total_pages}", callback_data=f"{prefix}:noop")
    if has_next:
        builder.button(text="➡️", callback_data=f"{prefix}:{kind}:{page + 1}")


def confirm_kb(prefix: str = "reg") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Подтвердить", callback_data=f"{prefix}:confirm")
    builder.button(text="🔄 Изменить", callback_data=f"{prefix}:restart")
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    builder.adjust(1)
    return builder.as_markup()


def settings_kb(notifications_enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Изменить группу", callback_data="set:change")
    toggle = "🔕 Выключить уведомления" if notifications_enabled else "🔔 Включить уведомления"
    builder.button(text=toggle, callback_data="set:toggle")
    builder.button(text="⬅️ В меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Статистика", callback_data="menu:stats")
    builder.button(text="🔄 Обновить кэш", callback_data="menu:refresh")
    builder.button(text="⬅️ В меню", callback_data="menu:home")
    builder.adjust(1)
    return builder.as_markup()


def cancel_kb(prefix: str = "reg") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data=f"{prefix}:cancel")
    return builder.as_markup()
