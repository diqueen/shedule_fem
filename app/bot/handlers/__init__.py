"""Root router assembly."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.handlers import admin, registration, schedule, settings, start
from app.bot.keyboards import cancel_kb


def build_router() -> Router:
    root = Router(name="root")
    root.include_router(start.router)
    root.include_router(registration.router)
    root.include_router(settings.router)
    root.include_router(schedule.router)
    root.include_router(admin.router)
    root.include_router(_fallback_router())
    return root


def _fallback_router() -> Router:
    router = Router(name="fallback")

    @router.message(StateFilter("*"))
    async def on_any_message(message: Message, state: FSMContext) -> None:
        current = await state.get_state()
        if current is not None:
            await message.answer(
                "Пожалуйста, выберите вариант из меню ниже или нажмите «Отмена».",
                reply_markup=cancel_kb(),
            )
        else:
            await message.answer(
                "Я бот с расписанием СПбГТИ(ТУ). Используйте /start или /help."
            )

    @router.callback_query()
    async def on_unknown_callback(callback: CallbackQuery) -> None:
        await callback.answer("Кнопка устарела, начните заново: /start", show_alert=False)

    return router
