"""Registration flow: education -> faculty -> course -> group -> confirm."""
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
    summary_text,
)
from app.bot.keyboards import (
    cancel_kb,
    confirm_kb,
    course_kb,
    education_kb,
    faculty_kb,
    group_kb,
    main_menu_kb,
)
from app.bot.states import Registration
from app.parser.exceptions import ScheduleError

logger = logging.getLogger(__name__)
router = Router(name="registration")


async def begin_registration(message: Message, state: FSMContext, services: Services) -> None:
    await state.clear()
    try:
        catalog = await services.schedule.get_catalog()
    except ScheduleError as exc:
        await message.answer(
            "⚠️ Не удалось получить список направлений с сайта. Попробуйте позже.",
        )
        logger.warning("Catalog load failed: %s", exc)
        return
    await state.set_state(Registration.education)
    await message.answer(
        "Выберите уровень обучения:",
        reply_markup=education_kb(catalog.education_levels),
    )


@router.callback_query(F.data == "reg:start")
async def on_start_registration(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    await callback.answer()
    if callback.message is not None:
        await begin_registration(callback.message, state, services)


@router.message(Command("register"))
async def on_register_command(message: Message, state: FSMContext, services: Services) -> None:
    await begin_registration(message, state, services)


@router.callback_query(Registration.education, F.data.startswith("reg:edu:"))
async def on_education(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    education_id = callback.data.split(":")[2]
    catalog = await services.schedule.get_catalog()
    level = find_level(catalog, education_id)
    if level is None:
        await callback.answer("Уровень не найден, начните заново", show_alert=True)
        return
    await state.update_data(reg_education_id=level.id, reg_education_name=level.name)
    await state.set_state(Registration.faculty)
    await callback.answer()
    specials = catalog.specialities_for(level.id)
    if callback.message is not None:
        await callback.message.edit_text(
            f"Уровень: {level.name}\nВыберите факультет/направление:",
            reply_markup=faculty_kb(specials, 0),
        )


@router.callback_query(Registration.faculty, F.data.startswith("reg:fac:"))
async def on_faculty_page(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    page = int(callback.data.split(":")[2])
    data = await state.get_data()
    catalog = await services.schedule.get_catalog()
    specials = catalog.specialities_for(data.get("reg_education_id", ""))
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=faculty_kb(specials, page))


@router.callback_query(Registration.faculty, F.data.startswith("reg:spec:"))
async def on_faculty(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    special_id = callback.data.split(":")[2]
    catalog = await services.schedule.get_catalog()
    special = find_special(catalog, special_id)
    if special is None:
        await callback.answer("Направление не найдено, начните заново", show_alert=True)
        return
    await state.update_data(reg_special_id=special.id, reg_special_name=special.name)
    await state.set_state(Registration.course)
    await callback.answer()
    courses = catalog.courses_for(special.id)
    if callback.message is not None:
        await callback.message.edit_text(
            f"Направление: {special.name}\nВыберите курс:",
            reply_markup=course_kb(courses),
        )


@router.callback_query(Registration.course, F.data.startswith("reg:course:"))
async def on_course(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    course = int(callback.data.split(":")[2])
    data = await state.get_data()
    special_name = data.get("reg_special_name")
    await callback.answer()
    try:
        groups = await load_groups(services, special_name, course)
    except ScheduleError as exc:
        logger.warning("Groups load failed: %s", exc)
        if callback.message is not None:
            await callback.message.edit_text(
                "⚠️ Не удалось получить список групп. Попробуйте ещё раз позже.",
                reply_markup=cancel_kb(),
            )
        return
    if not groups:
        if callback.message is not None:
            await callback.message.edit_text(
                "Для этого курса группы не найдены. Выберите другой курс.",
                reply_markup=cancel_kb(),
            )
        return
    await state.update_data(reg_course=course, reg_groups=groups_as_dicts(groups))
    await state.set_state(Registration.group)
    if callback.message is not None:
        await callback.message.edit_text(
            "Выберите группу:", reply_markup=group_kb(groups, 0)
        )


@router.callback_query(Registration.group, F.data.startswith("reg:groups:"))
async def on_groups_page(callback: CallbackQuery, state: FSMContext) -> None:
    page = int(callback.data.split(":")[2])
    data = await state.get_data()
    groups = groups_from_dicts(data.get("reg_groups"))
    await callback.answer()
    if callback.message is not None:
        await callback.message.edit_reply_markup(reply_markup=group_kb(groups, page))


@router.callback_query(Registration.group, F.data.startswith("reg:group:"))
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
    await state.set_state(Registration.confirm)
    await callback.answer()
    text = summary_text(
        data.get("reg_education_name", ""),
        data.get("reg_special_name", ""),
        data.get("reg_course", 0),
        group.name,
    )
    if callback.message is not None:
        await callback.message.edit_text(text, reply_markup=confirm_kb())


@router.callback_query(Registration.confirm, F.data == "reg:confirm")
async def on_confirm(
    callback: CallbackQuery, state: FSMContext, services: Services
) -> None:
    data = await state.get_data()
    user = callback.from_user
    profile = await services.users.register(
        telegram_id=user.id,
        username=user.username,
        education_level=data.get("reg_education_name", ""),
        faculty=data.get("reg_special_name", ""),
        course=int(data.get("reg_course", 0)),
        group_id=data.get("reg_group_id", ""),
        group_name=data.get("reg_group_name", ""),
    )
    await state.clear()
    await callback.answer("Готово!")
    if callback.message is not None:
        await callback.message.edit_text(
            "✅ Регистрация завершена!\n\n"
            f"🎓 Уровень: {profile.education_level}\n"
            f"🏛 Факультет: {profile.faculty}\n"
            f"📚 Курс: {profile.course}\n"
            f"👥 Группа: {profile.group_name}\n\n"
            "Теперь вы можете смотреть расписание и получать его автоматически.",
        )
        await callback.message.answer(
            "Главное меню:", reply_markup=main_menu_kb(True, services.settings.is_admin(user.id))
        )


@router.callback_query(Registration.confirm, F.data == "reg:restart")
async def on_restart(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await callback.answer()
    if callback.message is not None:
        await begin_registration(callback.message, state, services)


@router.callback_query(F.data == "reg:cancel")
async def on_cancel(callback: CallbackQuery, state: FSMContext, services: Services) -> None:
    await state.clear()
    await callback.answer("Отменено")
    if callback.message is not None:
        profile = await services.users.get(callback.from_user.id)
        await callback.message.edit_text(
            "Отменено. Главное меню:",
            reply_markup=main_menu_kb(profile is not None, services.settings.is_admin(callback.from_user.id)),
        )
