"""Shared pytest fixtures. Parser tests never touch the network."""
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from app.config import Settings
from app.database.database import Database
from app.parser.models import Catalog
from app.parser.parser import parse_catalog

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def main_page_html() -> str:
    return (FIXTURES / "main_page.html").read_text(encoding="utf-8")


@pytest.fixture
def october_html() -> str:
    return (FIXTURES / "schedule_october.html").read_text(encoding="utf-8")


@pytest.fixture
def september_html() -> str:
    return (FIXTURES / "schedule_september.html").read_text(encoding="utf-8")


@pytest.fixture
def november_html() -> str:
    return (FIXTURES / "schedule_november.html").read_text(encoding="utf-8")


@pytest.fixture
def groups_json() -> str:
    return (FIXTURES / "groups.json").read_text(encoding="utf-8")


@pytest.fixture
def months_json() -> str:
    return (FIXTURES / "months.json").read_text(encoding="utf-8")


@pytest.fixture
def catalog(main_page_html: str) -> Catalog:
    return parse_catalog(main_page_html)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        bot_token="test-token",
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        timezone="Europe/Moscow",
        schedule_send_time="20:00",
        schedule_cache_ttl=3600,
        schedule_url="https://example.test/raspisanie/",
        admin_ids="1,2",
        log_level="WARNING",
    )


@pytest_asyncio.fixture
async def db(settings: Settings):
    database = Database(settings.database_url)
    await database.create_all()
    yield database
    await database.dispose()
