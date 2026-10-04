"""User profile management."""
from __future__ import annotations

from dataclasses import dataclass

from app.database.database import Database
from app.database.models import User
from app.database.repositories import UserRepository


@dataclass(slots=True)
class UserStats:
    total: int
    enabled: int


class UserService:
    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, telegram_id: int) -> User | None:
        async with self.db.session() as session:
            return await UserRepository(session).get_by_telegram_id(telegram_id)

    async def register(
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
        async with self.db.session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if user is None:
                user = await repo.create(
                    telegram_id=telegram_id,
                    username=username,
                    education_level=education_level,
                    faculty=faculty,
                    course=course,
                    group_id=group_id,
                    group_name=group_name,
                )
            else:
                await repo.update_profile(
                    user,
                    education_level=education_level,
                    faculty=faculty,
                    course=course,
                    group_id=group_id,
                    group_name=group_name,
                )
                await repo.update_username(user, username)
            return user

    async def update_profile(
        self,
        telegram_id: int,
        *,
        education_level: str,
        faculty: str,
        course: int,
        group_id: str,
        group_name: str,
    ) -> User | None:
        async with self.db.session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if user is None:
                return None
            return await repo.update_profile(
                user,
                education_level=education_level,
                faculty=faculty,
                course=course,
                group_id=group_id,
                group_name=group_name,
            )

    async def set_notifications(self, telegram_id: int, enabled: bool) -> User | None:
        async with self.db.session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_telegram_id(telegram_id)
            if user is None:
                return None
            return await repo.set_notifications(user, enabled)

    async def toggle_notifications(self, telegram_id: int) -> User | None:
        user = await self.get(telegram_id)
        if user is None:
            return None
        return await self.set_notifications(telegram_id, not user.notifications_enabled)

    async def list_for_notifications(self) -> list[User]:
        async with self.db.session() as session:
            return await UserRepository(session).list_with_notifications()

    async def stats(self) -> UserStats:
        async with self.db.session() as session:
            repo = UserRepository(session)
            return UserStats(total=await repo.count_all(), enabled=await repo.count_enabled())
