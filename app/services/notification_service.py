"""Automatic and on-demand schedule message delivery."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from app.config import Settings
from app.database.database import Database
from app.database.models import User
from app.database.repositories import NotificationLogRepository, UserRepository
from app.services.schedule_service import DayResult, ScheduleService
from app.utils.dates import tomorrow_in
from app.utils.formatting import (
    format_day_schedule,
    format_no_lessons,
    format_not_published,
    format_stale_notice,
    format_tomorrow_source_error,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NotificationReport:
    day: date | None = None
    total: int = 0
    sent: int = 0
    skipped: int = 0
    blocked: int = 0
    failed: int = 0
    groups: int = 0
    errors: list[str] = field(default_factory=list)


def build_day_message(group_name: str, day: date, result: DayResult) -> str:
    if result.status == "ok":
        message = format_day_schedule(group_name, day, result.entries)
        if result.stale or result.error:
            message = f"{message}\n\n{format_stale_notice()}"
        return message
    if result.status == "no_lessons":
        return format_no_lessons(group_name, day)
    if result.status == "not_published":
        return format_not_published(group_name, day)
    # stale without data or hard error
    return format_tomorrow_source_error()


class NotificationService:
    def __init__(
        self,
        bot: Bot,
        db: Database,
        schedule_service: ScheduleService,
        settings: Settings,
    ) -> None:
        self.bot = bot
        self.db = db
        self.schedule_service = schedule_service
        self.settings = settings

    async def send_tomorrow(self, *, day: date | None = None) -> NotificationReport:
        day = day or tomorrow_in(self.settings.timezone)
        report = NotificationReport(day=day)

        async with self.db.session() as session:
            users = await UserRepository(session).list_with_notifications()
        report.total = len(users)

        # Group users so the website is queried once per group, not per user.
        groups: dict[tuple[str, str, int], list[User]] = {}
        for user in users:
            groups.setdefault((user.group_id, user.faculty, user.course), []).append(user)
        report.groups = len(groups)

        for (group_id, faculty, course), group_users in groups.items():
            try:
                result = await self.schedule_service.get_day(group_id, faculty, course, day)
            except Exception as exc:  # noqa: BLE001 - never let one group kill the run
                logger.exception("Failed to load schedule for group %s: %s", group_id, exc)
                report.errors.append(f"{group_id}: {exc}")
                result = DayResult(day, [], "error", error=str(exc))

            for user in group_users:
                await self._send_one(user, day, result, report)

        logger.info(
            "Notification completed day=%s total=%s sent=%s skipped=%s blocked=%s failed=%s",
            day, report.total, report.sent, report.skipped, report.blocked, report.failed,
        )
        return report

    async def _send_one(
        self,
        user: User,
        day: date,
        result: DayResult,
        report: NotificationReport,
    ) -> None:
        async with self.db.session() as session:
            existing = await NotificationLogRepository(session).get(user.id, day)
        if existing is not None and existing.status == "sent":
            report.skipped += 1
            return

        message = build_day_message(user.group_name, day, result)
        try:
            await self.bot.send_message(user.telegram_id, message, parse_mode="HTML")
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await self.bot.send_message(user.telegram_id, message, parse_mode="HTML")
            except Exception as retry_exc:  # noqa: BLE001
                await self._record(user, day, "error", str(retry_exc))
                report.failed += 1
                report.errors.append(f"{user.telegram_id}: {retry_exc}")
                return
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            await self._handle_blocked(user, day, exc)
            report.blocked += 1
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegram send failed for user %s: %s", user.telegram_id, exc)
            await self._record(user, day, "error", str(exc))
            report.failed += 1
            report.errors.append(f"{user.telegram_id}: {exc}")
            return

        await self._record(user, day, "sent", None)
        report.sent += 1

    async def _handle_blocked(self, user: User, day: date, exc: Exception) -> None:
        logger.info("User %s blocked the bot, disabling notifications", user.telegram_id)
        async with self.db.session() as session:
            repo = UserRepository(session)
            fresh = await repo.get_by_id(user.id)
            if fresh is not None:
                await repo.set_notifications(fresh, False)
            await NotificationLogRepository(session).upsert(
                user_id=user.id, day=day, status="blocked", error_message=str(exc)
            )

    async def _record(self, user: User, day: date, status: str, error: str | None) -> None:
        async with self.db.session() as session:
            await NotificationLogRepository(session).upsert(
                user_id=user.id, day=day, status=status, error_message=error
            )
