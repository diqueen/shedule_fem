"""Async HTTP client for the schedule website.

The site is a Bitrix page that loads its data via POST requests to the very
same URL. Three payload shapes are used (all discovered from the site's own
``timetable.new`` component JavaScript):

* ``{special, course}``                  -> JSON list of ``[name, id]`` groups
* ``{special, course, group}``           -> JSON list of month names
* ``{special, course, group, month}``    -> HTML fragment with the table

This module knows *nothing* about Telegram or the database.
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.parser.exceptions import ScheduleSourceError, ScheduleStructureError
from app.parser.models import GroupRef

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


class ScheduleClient:
    def __init__(
        self,
        bases: list[str],
        *,
        timeout: float = 30.0,
        verify_tls: bool = False,
        retries: int = 2,
        retry_backoff: float = 1.5,
    ) -> None:
        if not bases:
            raise ValueError("At least one base URL is required")
        self._bases = list(bases)
        self._preferred: str | None = None
        self._retries = retries
        self._retry_backoff = retry_backoff
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
            verify=verify_tls,
            follow_redirects=True,
            headers={
                "User-Agent": _USER_AGENT,
                "X-Requested-With": "XMLHttpRequest",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )

    @property
    def bases(self) -> list[str]:
        return list(self._bases)

    def _ordered_bases(self) -> list[str]:
        if self._preferred and self._preferred in self._bases:
            return [self._preferred] + [b for b in self._bases if b != self._preferred]
        return list(self._bases)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> ScheduleClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def _post(self, data: dict[str, str]) -> str:
        last_error: Exception | None = None
        for base in self._ordered_bases():
            for attempt in range(1, self._retries + 1):
                try:
                    response = await self._client.post(base, data=data)
                    response.raise_for_status()
                    self._preferred = base
                    return response.text
                except httpx.HTTPError as exc:
                    last_error = exc
                    logger.warning(
                        "Schedule request failed (base=%s attempt=%s): %s", base, attempt, exc
                    )
                    if attempt < self._retries:
                        await asyncio.sleep(self._retry_backoff * attempt)
        raise ScheduleSourceError(f"Schedule source unavailable: {last_error}") from last_error

    async def get_catalog_html(self) -> str:
        """Return the main schedule page HTML (used to build the filter catalog)."""
        last_error: Exception | None = None
        for base in self._ordered_bases():
            try:
                response = await self._client.get(base)
                response.raise_for_status()
                self._preferred = base
                return response.text
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning("Catalog request failed (base=%s): %s", base, exc)
        raise ScheduleSourceError(f"Schedule source unavailable: {last_error}") from last_error

    async def get_groups(self, special: str, course: int) -> list[GroupRef]:
        text = await self._post({"special": special, "course": str(course)})
        return _parse_groups(text)

    async def get_months(self, special: str, course: int, group: str) -> list[str]:
        text = await self._post({"special": special, "course": str(course), "group": group})
        return _parse_months(text)

    async def get_month_html(self, special: str, course: int, group: str, month: str) -> str:
        return await self._post(
            {"special": special, "course": str(course), "group": group, "month": month}
        )


def _parse_groups(text: str) -> list[GroupRef]:
    import json

    text = text.strip()
    if not text.startswith("["):
        raise ScheduleStructureError("Expected JSON group list, got HTML page")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScheduleStructureError(f"Invalid group JSON: {exc}") from exc
    groups: list[GroupRef] = []
    for item in data or []:
        if isinstance(item, list) and len(item) >= 2:
            groups.append(GroupRef(name=str(item[0]).strip(), external_id=str(item[1]).strip()))
        elif isinstance(item, str):
            groups.append(GroupRef(name=item.strip(), external_id=item.strip()))
    return groups


def _parse_months(text: str) -> list[str]:
    import json

    text = text.strip()
    if not text.startswith("["):
        raise ScheduleStructureError("Expected JSON month list, got HTML page")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ScheduleStructureError(f"Invalid month JSON: {exc}") from exc
    return [str(m).strip() for m in (data or []) if str(m).strip()]
