"""/settings and the "change group" flow."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.container import Services
from app.bot.handlers.flow_common import (
    find_level,
    find_special,
    groups_as_dicts,
    groups_from_dicts,
    load_groups,
    profile_text,
    summary_text,
)
from app.bot.keyboards import (
    cancel_kb,
    confirm_kb,
    course_kb,
    education_kb,
    faculty_kb,
    group_kb,
    settings_kb,
)
from app.bot.states import SettingsFlow
from app.parser.exceptions import ScheduleError

logger = logging.getLogger(__name__)
router = Router(name="settings")


async def show_settings(message: Message, services: Services) -> None:
    profile = await services.users.get(message.from_user.id)
    if profile is None:
        await message.answer("Сначала выберите группу командой /start.")
        return
    await message.answer(
        profile_text(profile),
        parse_mode="HTML",
        reply_markup=settings_kb(profile.notifications_enabled),
    )


@router.message(Command("settings"))
async def on_settings(message: Message, state: FSMContext, services: Services) -> None:
    await state.clear()
    await show_settings(message, services)


@router.callback_query(F.data == "set:menu")
async def cb_settings(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await callback.answer()
    await state.clear()
    profile = await services.users.get(callback.from_user.id)
    if profile is None or callback.message is None:
        return
    await callback.message.edit_text(
        profile_text(profile),
        parse_mode="HTML",
        reply_markup=settings_kb(profile.notifications_enabled),
    )


@router.callback_query(F.data == "set:toggle")
async def cb_toggle(callback: CallbackQuery, services: Services) -> None:
    profile = await services.users.toggle_notifications(callback.from_user.id)
    if profile is None:
        await callback.answer("Профиль не найден", show_alert=True)
        return
    state_text = "включены" if profile.notifications_enabled else "выключены"
    await callback.answer(f"Уведомления {state_text}")
    if callback.message is not None:
        await callback.message.edit_text(
            profile_text(profile),
            parse_mode="HTML",
            reply_markup=settings_kb(profile.notifications_enabled),
        )


async def begin_change(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await state.clear()
    try:
        catalog = await services.schedule.get_catalog()
    except ScheduleError as exc:
        logger.warning("Catalog load failed: %s", exc)
        await callback.answer("Не удалось загрузить список. Попробуйте позже.", show_alert=True)
        return
    await state.set_state(SettingsFlow.education)
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите уровень обучения:",
            reply_markup=education_kb(catalog.education_levels, prefix="set"),
        )


@router.callback_query(F.data == "set:change")
async def cb_change(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await callback.answer()
    await begin_change(callback, state, services)


@router.callback_query(SettingsFlow.education, F.data.startswith("set:edu:"))
async def on_education(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    education_id = callback.data.split(":")[2]
    catalog = await services.schedule.get_catalog()
    level = find_level(catalog, education_id)
    if level is None:
        await callback.answer("Уровень не найден, начните заново", show_alert=True)
        return
    await state.update_data(reg_education_id=level.id, reg_education_name=level.name)
    await state.set_state(SettingsFlow.faculty)
    await callback.answer()
    specials = catalog.specialities_for(level.id)
    if callback.message is not None:
        await callback.message.edit_text(
            f"Уровень: {level.name}\nВыберите факультет/направление:",
            reply_markup=faculty_kb(specials, 0, prefix="set"),
        )


@router.callback_query(SettingsFlow.faculty, F.data.startswith("set:fac:"))
async def on_faculty_page(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    page = int(callback.data.split(":")[2])
    data = await state.get_data()
    catalog = await services.schedule.get_catalog()
    specials = catalog.specialities_for(data.get("reg_education_id", ""))
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=faculty_kb(specials, page, prefix="set")
        )


@router.callback_query(SettingsFlow.faculty, F.data.startswith("set:spec:"))
async def on_faculty(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    special_id = callback.data.split(":")[2]
    catalog = await services.schedule.get_catalog()
    special = find_special(catalog, special_id)
    if special is None:
        await callback.answer("Направление не найдено, начните заново", show_alert=True)
        return
    await state.update_data(reg_special_id=special.id, reg_special_name=special.name)
    await state.set_state(SettingsFlow.course)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            f"Направление: {special.name}\nВыберите курс:",
            reply_markup=course_kb(catalog.courses_for(special.id), prefix="set"),
        )


@router.callback_query(SettingsFlow.course, F.data.startswith("set:course:"))
async def on_course(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    course = int(callback.data.split(":")[2])
    data = await state.get_data()
    await callback.answer()
    try:
        groups = await load_groups(services, data.get("reg_special_name"), course)
    except ScheduleError as exc:
        logger.warning("Groups load failed: %s", exc)
        if callback.message is not None:
            await callback.message.edit_text(
                "⚠️ Не удалось получить список групп. Попробуйте позже.",
                reply_markup=cancel_kb("set"),
            )
        return
    if not groups:
        if callback.message is not None:
            await callback.message.edit_text(
                "Для этого курса группы не найдены. Выберите другой курс.",
                reply_markup=cancel_kb("set"),
            )
        return
    await state.update_data(reg_course=course, reg_groups=groups_as_dicts(groups))
    await state.set_state(SettingsFlow.group)
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите группу:", reply_markup=group_kb(groups, 0, prefix="set")
        )


@router.callback_query(SettingsFlow.group, F.data.startswith("set:groups:"))
async def on_groups_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[2])
    data = await state.get_data()
    groups = groups_from_dicts(data.get("reg_groups"))
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(
            reply_markup=group_kb(groups, page, prefix="set")
        )


@router.callback_query(SettingsFlow.group, F.data.startswith("set:group:"))
async def on_group(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    index = int(parts[3])
    data = await state.get_data()
    groups = groups_from_dicts(data.get("reg_groups"))
    if index < 0 or index >= len(groups):
        await callback.answer("Группа не найдена, начните заново", show_alert=True)
        return
    group = groups[index]
    await state.update_data(reg_group_name=group.name, reg_group_id=group.external_id)
    await state.set_state(SettingsFlow.confirm)
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_text(
            summary_text(
                data.get("reg_education_name", ""),
                data.get("reg_special_name", ""),
                data.get("reg_course", 0),
                group.name,
            ),
            reply_markup=confirm_kb("set"),
        )


@router.callback_query(SettingsFlow.confirm, F.data == "set:confirm")
async def on_confirm(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    data = await state.get_data()
    profile = await services.users.update_profile(
        callback.from_user.id,
        education_level=data.get("reg_education_name", ""),
        faculty=data.get("reg_special_name", ""),
        course=int(data.get("reg_course", 0)),
        group_id=data.get("reg_group_id", ""),
        group_name=data.get("reg_group_name", ""),
    )
    await state.clear()
    await callback.answer("Сохранено")
    if profile is not None and callback.message is not None:
        await callback.message.edit_text(
            profile_text(profile),
            parse_mode="HTML",
            reply_markup=settings_kb(profile.notifications_enabled),
        )


@router.callback_query(SettingsFlow.confirm, F.data == "set:restart")
async def on_restart(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await callback.answer()
    await begin_change(callback, state, services)


@router.callback_query(F.data == "set:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await state.clear()
    await callback.answer("Отменено")
    profile = await services.users.get(callback.from_user.id)
    if profile is not None and callback.message is not None:
        await callback.message.edit_text(
            profile_text(profile),
            parse_mode="HTML",
            reply_markup=settings_kb(profile.notifications_enabled),
        )
