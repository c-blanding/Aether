from __future__ import annotations

from abc import ABC, abstractmethod

from aether.domain.world import World
from aether.repositories.base import NotFoundError


class WorldRepository(ABC):
    """Persistence port for World aggregates."""

    @abstractmethod
    def get(self, world_id: str) -> World:
        ...

    @abstractmethod
    def save(self, world: World) -> World:
        ...

    @abstractmethod
    def delete(self, world_id: str) -> None:
        ...

    @abstractmethod
    def exists(self, world_id: str) -> bool:
        ...

    @abstractmethod
    def list(self) -> list[World]:
        ...


class InMemoryWorldRepository(WorldRepository):
    """Process-local World store. Swap for a DB-backed implementation later."""

    def __init__(self) -> None:
        self._worlds: dict[str, World] = {}

    def get(self, world_id: str) -> World:
        world = self._worlds.get(world_id)
        if world is None:
            raise NotFoundError(f"World not found: {world_id}")
        return world

    def save(self, world: World) -> World:
        self._worlds[world.id] = world
        return world

    def delete(self, world_id: str) -> None:
        """Idempotent: missing IDs are a no-op."""
        self._worlds.pop(world_id, None)

    def exists(self, world_id: str) -> bool:
        return world_id in self._worlds

    def list(self) -> list[World]:
        return list(self._worlds.values())
