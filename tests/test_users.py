"""User repository / service tests."""
from __future__ import annotations

import pytest

from app.database.repositories import UserRepository, group_tokens
from app.services.user_service import UserService


async def _register(service: UserService, telegram_id: int = 100, group: str = "6511,6512"):
    return await service.register(
        telegram_id=telegram_id,
        username="tester",
        education_level="Бакалавриат",
        faculty="Экономика",
        course=2,
        group_id=group,
        group_name=group,
    )


@pytest.mark.asyncio
async def test_create_and_find_user(db):
    service = UserService(db)
    user = await _register(service)
    assert user.id is not None
    assert user.group_id == "6511,6512"

    found = await service.get(100)
    assert found is not None
    assert found.telegram_id == 100
    assert found.notifications_enabled is True


@pytest.mark.asyncio
async def test_register_twice_updates_profile(db):
    service = UserService(db)
    await _register(service)
    updated = await service.register(
        telegram_id=100,
        username="tester2",
        education_level="Бакалавриат",
        faculty="Маркетинг",
        course=3,
        group_id="6441",
        group_name="6441",
    )
    assert updated.faculty == "Маркетинг"
    assert updated.course == 3
    assert updated.group_id == "6441"

    async with db.session() as session:
        total = await UserRepository(session).count_all()
    assert total == 1


@pytest.mark.asyncio
async def test_change_group(db):
    service = UserService(db)
    await _register(service)
    changed = await service.update_profile(
        100,
        education_level="Бакалавриат",
        faculty="Логистика",
        course=2,
        group_id="6561",
        group_name="6561",
    )
    assert changed is not None
    assert changed.group_id == "6561"
    assert changed.faculty == "Логистика"


@pytest.mark.asyncio
async def test_toggle_notifications(db):
    service = UserService(db)
    await _register(service)
    off = await service.set_notifications(100, False)
    assert off is not None and off.notifications_enabled is False

    on = await service.toggle_notifications(100)
    assert on is not None and on.notifications_enabled is True


@pytest.mark.asyncio
async def test_list_for_notifications_excludes_disabled(db):
    service = UserService(db)
    await _register(service, telegram_id=1)
    await _register(service, telegram_id=2)
    await service.set_notifications(2, False)

    recipients = await service.list_for_notifications()
    assert [u.telegram_id for u in recipients] == [1]

    stats = await service.stats()
    assert stats.total == 2
    assert stats.enabled == 1


@pytest.mark.asyncio
async def test_find_missing_user_returns_none(db):
    service = UserService(db)
    assert await service.get(999999) is None


def test_group_tokens_expansion():
    tokens = group_tokens("6511,6512")
    assert set(tokens) == {"6511,6512", "6511", "6512"}
