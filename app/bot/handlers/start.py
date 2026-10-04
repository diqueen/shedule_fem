"""Start / help / main menu."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.container import Services
from app.bot.keyboards import main_menu_kb

router = Router(name="start")

GREETING_NEW = (
    "Привет!\n\n"
    "Я бот с расписанием СПбГТИ(ТУ) (ФЭМ).\n\n"
    "Чтобы получать расписание автоматически, нужно выбрать:\n"
    "• уровень обучения\n"
    "• факультет\n"
    "• курс\n"
    "• группу"
)

HELP_TEXT = (
    "ℹ️ <b>Доступные команды</b>\n\n"
    "/start — регистрация и главное меню\n"
    "/schedule — расписание на ближайший день\n"
    "/tomorrow — расписание на завтра\n"
    "/week — расписание на текущую неделю\n"
    "/month — расписание на текущий месяц\n"
    "/settings — настройки группы и уведомлений\n"
    "/help — эта справка\n\n"
    "Расписание берётся с официального сайта gtifem.ru и обновляется автоматически."
)


@router.message(CommandStart())
async def on_start(message: Message, state: FSMContext, services: Services) -> None:
    await state.clear()
    profile = await services.users.get(message.from_user.id)
    is_admin = services.settings.is_admin(message.from_user.id)
    if profile is None:
        await message.answer(GREETING_NEW, reply_markup=main_menu_kb(False, is_admin))
    else:
        await message.answer(
            f"С возвращением, {profile.group_name}!\n\nГлавное меню:",
            reply_markup=main_menu_kb(True, is_admin),
        )


@router.message(Command("help"))
async def on_help(message: Message, services: Services) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "menu:help")
async def on_help_callback(callback: CallbackQuery, services: Services) -> None:
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(HELP_TEXT, parse_mode="HTML")


@router.callback_query(F.data == "menu:home")
async def on_home(callback: CallbackQuery, services: Services) -> None:
    await callback.answer()
    profile = await services.users.get(callback.from_user.id)
    is_admin = services.settings.is_admin(callback.from_user.id)
    if callback.message is not None:
        await callback.message.edit_text(
            "Главное меню:", reply_markup=main_menu_kb(profile is not None, is_admin)
        )
