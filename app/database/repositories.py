"""Repository layer: all SQL lives here (handlers/services never write SQL)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import (
    Group,
    NotificationLog,
    ScheduleEntry,
    ScheduleFetchLog,
    User,
)


def group_tokens(group_id: str) -> list[str]:
    """Expand ``"6511,6512"`` into ``["6511,6512", "6511", "6512"]``.

    Lessons may reference several groups at once; matching by any token keeps a
    lesson visible to every listed group while ``IN`` + a set removes duplicates.
    """
    tokens = {group_id.strip()}
    for part in group_id.split(","):
        part = part.strip()
        if part:
            tokens.add(part)
    return [t for t in tokens if t]


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def create(
        self,
        *,
        telegram_id: int,
        username: str | None,
        education_level: str,
        faculty: str,
        course: int,
        group_id: str,
        group_name: str,
    ) -> User:
        user = User(
            telegram_id=telegram_id,
            username=username,
            education_level=education_level,
            faculty=faculty,
            course=course,
            group_id=group_id,
            group_name=group_name,
        )
        self.session.add(user)
        await self.session.flush()
        return user

    async def update_profile(
        self,
        user: User,
        *,
        education_level: str,
        faculty: str,
        course: int,
        group_id: str,
        group_name: str,
    ) -> User:
        user.education_level = education_level
        user.faculty = faculty
        user.course = course
        user.group_id = group_id
        user.group_name = group_name
        await self.session.flush()
        return user

    async def set_notifications(self, user: User, enabled: bool) -> User:
        user.notifications_enabled = enabled
        await self.session.flush()
        return user

    async def update_username(self, user: User, username: str | None) -> None:
        if user.username != username:
            user.username = username
            await self.session.flush()

    async def list_with_notifications(self) -> list[User]:
        result = await self.session.execute(
            select(User).where(User.notifications_enabled.is_(True)).order_by(User.id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[User]:
        result = await self.session.execute(select(User).order_by(User.id))
        return list(result.scalars().all())

    async def count_all(self) -> int:
        return int(await self.session.scalar(select(func.count(User.id))) or 0)

    async def count_enabled(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count(User.id)).where(User.notifications_enabled.is_(True))
            )
            or 0
        )


class GroupRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert(
        self,
        *,
        external_id: str,
        name: str,
        education_level: str | None,
        faculty: str | None,
        course: int | None,
    ) -> Group:
        result = await self.session.execute(
            select(Group).where(Group.external_id == external_id)
        )
        group = result.scalar_one_or_none()
        if group is None:
            group = Group(
                external_id=external_id,
                name=name,
                education_level=education_level,
                faculty=faculty,
                course=course,
            )
            self.session.add(group)
        else:
            group.name = name
            group.education_level = education_level
            group.faculty = faculty
            group.course = course
        await self.session.flush()
        return group

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(Group.id))) or 0)

    async def list_all(self) -> list[Group]:
        result = await self.session.execute(select(Group).order_by(Group.external_id))
        return list(result.scalars().all())


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def replace_month(self, group_id: str, year: int, month: int, entries: list) -> int:
        """Replace all entries of a group for a month with fresh data."""
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        await self.session.execute(
            delete(ScheduleEntry).where(
                ScheduleEntry.group_id == group_id,
                ScheduleEntry.schedule_date >= start,
                ScheduleEntry.schedule_date < end,
            )
        )
        for entry in entries:
            self.session.add(entry)
        await self.session.flush()
        return len(entries)

    async def delete_month(self, group_id: str, year: int, month: int) -> None:
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        await self.session.execute(
            delete(ScheduleEntry).where(
                ScheduleEntry.group_id == group_id,
                ScheduleEntry.schedule_date >= start,
                ScheduleEntry.schedule_date < end,
            )
        )

    async def get_for_date(self, group_id: str, day: date) -> list[ScheduleEntry]:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                ScheduleEntry.group_id.in_(group_tokens(group_id)),
                ScheduleEntry.schedule_date == day,
            )
            .order_by(ScheduleEntry.start_time, ScheduleEntry.id)
        )
        return list(result.scalars().all())

    async def get_for_range(self, group_id: str, start: date, end: date) -> list[ScheduleEntry]:
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                ScheduleEntry.group_id.in_(group_tokens(group_id)),
                ScheduleEntry.schedule_date >= start,
                ScheduleEntry.schedule_date <= end,
            )
            .order_by(ScheduleEntry.schedule_date, ScheduleEntry.start_time, ScheduleEntry.id)
        )
        return list(result.scalars().all())

    async def get_for_month(self, group_id: str, year: int, month: int) -> list[ScheduleEntry]:
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        result = await self.session.execute(
            select(ScheduleEntry)
            .where(
                ScheduleEntry.group_id.in_(group_tokens(group_id)),
                ScheduleEntry.schedule_date >= start,
                ScheduleEntry.schedule_date < end,
            )
            .order_by(ScheduleEntry.schedule_date, ScheduleEntry.start_time, ScheduleEntry.id)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(ScheduleEntry.id))) or 0)

    async def count_for_month(self, year: int, month: int) -> int:
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        return int(
            await self.session.scalar(
                select(func.count(ScheduleEntry.id)).where(
                    ScheduleEntry.schedule_date >= start,
                    ScheduleEntry.schedule_date < end,
                )
            )
            or 0
        )

    async def distinct_group_count_for_month(self, year: int, month: int) -> int:
        start = date(year, month, 1)
        end = date(year + (month == 12), (month % 12) + 1, 1)
        return int(
            await self.session.scalar(
                select(func.count(func.distinct(ScheduleEntry.group_id))).where(
                    ScheduleEntry.schedule_date >= start,
                    ScheduleEntry.schedule_date < end,
                )
            )
            or 0
        )


class NotificationLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int, day: date) -> NotificationLog | None:
        result = await self.session.execute(
            select(NotificationLog).where(
                NotificationLog.user_id == user_id, NotificationLog.schedule_date == day
            )
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        user_id: int,
        day: date,
        status: str,
        error_message: str | None = None,
    ) -> NotificationLog:
        log = await self.get(user_id, day)
        if log is None:
            log = NotificationLog(user_id=user_id, schedule_date=day)
            self.session.add(log)
        log.status = status
        log.error_message = error_message
        log.sent_at = datetime.now(timezone.utc)
        await self.session.flush()
        return log


class ScheduleFetchLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, scope_key: str) -> ScheduleFetchLog | None:
        result = await self.session.execute(
            select(ScheduleFetchLog).where(ScheduleFetchLog.scope_key == scope_key)
        )
        return result.scalar_one_or_none()

    async def set_result(
        self,
        *,
        scope_key: str,
        year: int,
        month: int,
        group_id: str,
        status: str,
        entries_count: int,
        source_url: str | None,
        source_hash: str | None,
        error: str | None = None,
    ) -> ScheduleFetchLog:
        log = await self.get(scope_key)
        if log is None:
            log = ScheduleFetchLog(
                scope_key=scope_key,
                year=year,
                month=month,
                group_id=group_id,
            )
            self.session.add(log)
        log.status = status
        log.entries_count = entries_count
        log.source_url = source_url
        log.source_hash = source_hash
        log.error = error
        log.fetched_at = datetime.now(timezone.utc)
        await self.session.flush()
        return log

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(ScheduleFetchLog.id))) or 0)

    async def count_errors(self) -> int:
        return int(
            await self.session.scalar(
                select(func.count(ScheduleFetchLog.id)).where(ScheduleFetchLog.status == "error")
            )
            or 0
        )

    async def latest(self) -> ScheduleFetchLog | None:
        result = await self.session.execute(
            select(ScheduleFetchLog).order_by(ScheduleFetchLog.fetched_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()
