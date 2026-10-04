"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    bot_token: str = Field(default="", alias="BOT_TOKEN")
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@postgres:5432/schedule_bot",
        alias="DATABASE_URL",
    )
    timezone: str = Field(default="Europe/Moscow", alias="TIMEZONE")
    schedule_send_time: str = Field(default="20:00", alias="SCHEDULE_SEND_TIME")
    schedule_cache_ttl: int = Field(default=3600, alias="SCHEDULE_CACHE_TTL")
    schedule_url: str = Field(
        default="https://gtifem.ru/dekanat/raspisanie/", alias="SCHEDULE_URL"
    )
    schedule_url_fallbacks: str = Field(default="", alias="SCHEDULE_URL_FALLBACKS")
    admin_ids: str = Field(default="", alias="ADMIN_IDS")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug_html_dir: str = Field(default="", alias="DEBUG_HTML_DIR")
    schedule_tls_verify: bool = Field(default=False, alias="SCHEDULE_TLS_VERIFY")

    @field_validator("schedule_send_time")
    @classmethod
    def _validate_send_time(cls, value: str) -> str:
        parts = value.strip().split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError("SCHEDULE_SEND_TIME must be in HH:MM format")
        hours, minutes = int(parts[0]), int(parts[1])
        if not (0 <= hours < 24 and 0 <= minutes < 60):
            raise ValueError("SCHEDULE_SEND_TIME out of range")
        return f"{hours:02d}:{minutes:02d}"

    @property
    def send_hour(self) -> int:
        return int(self.schedule_send_time.split(":")[0])

    @property
    def send_minute(self) -> int:
        return int(self.schedule_send_time.split(":")[1])

    @property
    def admin_id_list(self) -> list[int]:
        return [int(x) for x in _split_csv(self.admin_ids) if x.lstrip("-").isdigit()]

    @property
    def schedule_bases(self) -> list[str]:
        bases = [self.schedule_url.strip()]
        bases.extend(_split_csv(self.schedule_url_fallbacks))
        return [b for b in bases if b]

    @property
    def debug_html_path(self) -> Path | None:
        value = self.debug_html_dir.strip()
        return Path(value) if value else None

    def is_admin(self, telegram_id: int) -> bool:
        return telegram_id in self.admin_id_list


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
