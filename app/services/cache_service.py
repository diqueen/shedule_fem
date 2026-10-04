"""Simple in-memory TTL cache.

PostgreSQL is the long-term store of normalized schedule data; this cache only
prevents redundant website requests within the TTL window. It is intentionally
process-local (no Redis) which is enough for the single-instance bot.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class _Item:
    value: Any
    expires_at: float


class CacheService:
    def __init__(self, default_ttl: int = 3600) -> None:
        self._default_ttl = default_ttl
        self._items: dict[str, _Item] = {}

    # -- generic API ------------------------------------------------------- #
    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = self._default_ttl if ttl is None else ttl
        self._items[key] = _Item(value=value, expires_at=time.monotonic() + ttl)

    def get(self, key: str) -> Any | None:
        item = self._items.get(key)
        if item is None:
            return None
        if item.expires_at < time.monotonic():
            self._items.pop(key, None)
            return None
        return item.value

    def is_fresh(self, key: str) -> bool:
        return self.get(key) is not None

    def invalidate(self, key: str) -> None:
        self._items.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        keys = [k for k in self._items if k.startswith(prefix)]
        for key in keys:
            self._items.pop(key, None)
        return len(keys)

    def clear(self) -> None:
        self._items.clear()

    def __len__(self) -> int:
        return len(self._items)

    # -- schedule-specific keys ------------------------------------------- #
    @staticmethod
    def month_key(year: int, month: int, group_id: str) -> str:
        return f"schedule:{year}:{month:02d}:{group_id}"

    @staticmethod
    def month_scope_prefix(year: int, month: int) -> str:
        return f"schedule:{year}:{month:02d}:"

    @staticmethod
    def catalog_key() -> str:
        return "catalog:main"
