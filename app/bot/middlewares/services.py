"""Middlewares that inject the service container and current user profile."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, User as TgUser

from app.bot.container import Services


class ServicesMiddleware(BaseMiddleware):
    def __init__(self, services: Services) -> None:
        self.services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        data["services"] = self.services
        data["settings"] = self.services.settings
        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    """Loads the stored profile (if any) into ``data['profile']``."""

    def __init__(self, services: Services) -> None:
        self.services = services

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        profile = None
        if tg_user is not None and not tg_user.is_bot:
            profile = await self.services.users.get(tg_user.id)
        data["profile"] = profile
        return await handler(event, data)


def is_private(event: TelegramObject) -> bool:
    if isinstance(event, Message):
        return event.chat.type == "private"
    if isinstance(event, CallbackQuery) and event.message is not None:
        return event.message.chat.type == "private"
    return False
