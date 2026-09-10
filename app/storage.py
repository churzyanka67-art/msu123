from time import monotonic
from typing import Protocol

from app.controller import Screen

Key = tuple[int, int]  # chat_id, user_id


class StateStore(Protocol):
    async def get(self, key: Key) -> Screen | None: ...
    async def set(self, key: Key, screen: Screen) -> None: ...


class MemoryStore:
    """Replace with persistent storage without changing screen transitions."""

    def __init__(self, ttl=86400, max_entries=10000):
        self.ttl, self.max_entries = ttl, max_entries
        self._items = {}

    async def get(self, key):
        item = self._items.get(key)
        if item and item[0] > monotonic():
            return item[1]
        self._items.pop(key, None)
        return None

    async def set(self, key, screen):
        now = monotonic()
        self._items = {k: v for k, v in self._items.items() if v[0] > now}
        if key not in self._items and len(self._items) >= self.max_entries:
            self._items.pop(next(iter(self._items)))
        self._items[key] = (now + self.ttl, screen)
