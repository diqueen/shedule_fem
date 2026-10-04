"""Admin commands: /stats, /refresh."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.container import Services
from app.database.repositories import (
    GroupRepository,
    ScheduleFetchLogRepository,
    ScheduleRepository,
)
from app.utils.dates import format_datetime_msk, month_name_ru, today_in

logger = logging.getLogger(__name__)
router = Router(name="admin")


async def _build_stats(services: Services) -> str:
    today = today_in(services.settings.timezone)
    async with services.db.session() as session:
        group_repo = GroupRepository(session)
        schedule_repo = ScheduleRepository(session)
        fetch_repo = ScheduleFetchLogRepository(session)
        users = await services.users.stats()
        groups_total = await group_repo.count()
        entries_month = await schedule_repo.count_for_month(today.year, today.month)
        groups_month = await schedule_repo.distinct_group_count_for_month(today.year, today.month)
        latest = await fetch_repo.latest()
        errors = await fetch_repo.count_errors()

    source_status = "OK" if errors == 0 else f"ошибок: {errors}"
    updated = format_datetime_msk(latest.fetched_at) if latest else "—"
    return (
        "📊 <b>Статистика</b>\n\n"
        f"Пользователей: {users.total}\n"
        f"Уведомления включены: {users.enabled}\n"
        f"Групп в каталоге: {groups_total}\n"
        f"Групп в кэше за месяц: {groups_month}\n"
        f"Записей за {month_name_ru(today.month)} {today.year}: {entries_month}\n\n"
        f"Кэш: {month_name_ru(today.month).capitalize()} {today.year}\n"
        f"Последнее обновление: {updated}\n"
        f"Источник: {source_status}"
    )


@router.message(Command("stats"))
async def on_stats(message: Message, services: Services) -> None:
    if not services.settings.is_admin(message.from_user.id):
        await message.answer("Команда доступна только администратору.")
        return
    await message.answer(await _build_stats(services), parse_mode="HTML")


@router.callback_query(F.data == "menu:stats")
async def cb_stats(callback: CallbackQuery, services: Services) -> None:
    if not services.settings.is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(await _build_stats(services), parse_mode="HTML")


@router.message(Command("refresh"))
async def on_refresh(message: Message, services: Services) -> None:
    if not services.settings.is_admin(message.from_user.id):
        await message.answer("Команда доступна только администратору.")
        return
    today = today_in(services.settings.timezone)
    status = await message.answer(
        f"🔄 Обновление...\nМесяц: {month_name_ru(today.month)} {today.year}"
    )
    report = await services.schedule.refresh_month(today.year, today.month)
    text = (
        "🔄 <b>Обновление завершено</b>\n\n"
        f"Месяц: {month_name_ru(report.month)} {report.year}\n"
        f"Групп: {report.groups}\n"
        f"Записей: {report.entries}\n"
        f"Статус: {'успешно' if report.status == 'ok' else 'частично'}\n"
        f"Время: {report.duration:.1f} с"
    )
    if report.errors:
        text += "\n\n⚠️ Ошибки:\n" + "\n".join(f"• {e}" for e in report.errors[:10])
    await status.edit_text(text, parse_mode="HTML")


@router.callback_query(F.data == "menu:refresh")
async def cb_refresh(callback: CallbackQuery, services: Services) -> None:
    if not services.settings.is_admin(callback.from_user.id):
        await callback.answer("Недоступно", show_alert=True)
        return
    await callback.answer("Запускаю обновление…")
    if callback.message is not None:
        await on_refresh(callback.message, services)
