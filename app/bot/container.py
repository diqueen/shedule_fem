"""Dependency container passed to handlers via middleware."""
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.database.database import Database
from app.parser.client import ScheduleClient
from app.services.cache_service import CacheService
from app.services.notification_service import NotificationService
from app.services.schedule_service import ScheduleService
from app.services.user_service import UserService


@dataclass(slots=True)
class Services:
    settings: Settings
    db: Database
    cache: CacheService
    client: ScheduleClient
    schedule: ScheduleService
    users: UserService
    notifications: NotificationService
