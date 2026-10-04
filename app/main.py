"""Application entry point: wires everything together and starts polling."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.container import Services
from app.bot.handlers import build_router
from app.bot.middlewares import ServicesMiddleware, UserMiddleware
from app.config import get_settings
from app.database.database import Database
from app.parser.client import ScheduleClient
from app.scheduler import setup_scheduler
from app.services.cache_service import CacheService
from app.services.notification_service import NotificationService
from app.services.schedule_service import ScheduleService
from app.services.user_service import UserService

logger = logging.getLogger("app")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        stream=sys.stdout,
    )
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def build_services() -> Services:
    settings = get_settings()
    db = Database(settings.database_url)
    cache = CacheService(default_ttl=settings.schedule_cache_ttl)
    client = ScheduleClient(settings.schedule_bases, verify_tls=settings.schedule_tls_verify)
    schedule = ScheduleService(client, db, cache, settings)
    users = UserService(db)
    return Services(
        settings=settings,
        db=db,
        cache=cache,
        client=client,
        schedule=schedule,
        users=users,
        notifications=None,  # type: ignore[arg-type]  # filled after Bot is created
    )


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set. Fill .env (see .env.example).")

    services = build_services()
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    services.notifications = NotificationService(bot, services.db, services.schedule, settings)

    await services.db.create_all()
    logger.info("Database connected")

    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(ServicesMiddleware(services))
    dispatcher.update.outer_middleware(UserMiddleware(services))
    dispatcher.include_router(build_router())

    scheduler = setup_scheduler(services)
    scheduler.start()
    logger.info("Scheduler started (daily broadcast at %s)", settings.schedule_send_time)

    me = await bot.get_me()
    logger.info("Bot started as @%s", me.username)

    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        logger.info("Shutting down...")
        scheduler.shutdown(wait=False)
        await services.client.close()
        await services.db.dispose()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code:
            print(exc.code)
