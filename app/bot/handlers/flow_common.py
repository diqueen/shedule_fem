"""Helpers shared by the registration and settings flows."""
from __future__ import annotations

from app.bot.container import Services
from app.parser.models import Catalog, GroupRef


def summary_text(education: str, faculty: str, course: int, group_name: str) -> str:
    return (
        "Проверьте данные:\n\n"
        f"🎓 Уровень: {education}\n"
        f"🏛 Факультет: {faculty}\n"
        f"📚 Курс: {course}\n"
        f"👥 Группа: {group_name}"
    )


def profile_text(profile) -> str:
    bell = "🔔 Уведомления: включены" if profile.notifications_enabled else "🔕 Уведомления: выключены"
    return (
        "⚙️ <b>Ваши настройки</b>\n\n"
        f"🎓 Уровень: {profile.education_level}\n"
        f"🏛 Факультет: {profile.faculty}\n"
        f"📚 Курс: {profile.course}\n"
        f"👥 Группа: {profile.group_name}\n"
        f"{bell}"
    )


def groups_as_dicts(groups: list[GroupRef]) -> list[dict[str, str]]:
    return [{"name": g.name, "external_id": g.external_id} for g in groups]


def groups_from_dicts(items: list[dict] | None) -> list[GroupRef]:
    return [GroupRef(name=i["name"], external_id=i["external_id"]) for i in (items or [])]


def find_level(catalog: Catalog, education_id: str):
    return next((lvl for lvl in catalog.education_levels if lvl.id == education_id), None)


def find_special(catalog: Catalog, special_id: str):
    return next((sp for sp in catalog.specialities if sp.id == special_id), None)


async def load_groups(services: Services, special_name: str, course: int) -> list[GroupRef]:
    return await services.schedule.get_groups(special_name, course)
