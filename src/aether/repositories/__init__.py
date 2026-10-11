from __future__ import annotations

from typing import TYPE_CHECKING

from aether.repositories.base import DuplicateError, NotFoundError, RepositoryError
from aether.repositories.character import (
    CharacterRepository,
    InMemoryCharacterRepository,
)
from aether.repositories.event import EventRepository, InMemoryEventRepository
from aether.repositories.session import InMemorySessionRepository, SessionRepository
from aether.repositories.store import InMemoryStore, Store
from aether.repositories.world import InMemoryWorldRepository, WorldRepository

if TYPE_CHECKING:
    from aether.repositories.postgres import (
        PostgresCharacterRepository,
        PostgresEventRepository,
        PostgresSessionRepository,
        PostgresWorldRepository,
    )
    from aether.repositories.store import PostgresStore

__all__ = [
    "RepositoryError",
    "NotFoundError",
    "DuplicateError",
    "Store",
    "InMemoryStore",
    "PostgresStore",
    "WorldRepository",
    "InMemoryWorldRepository",
    "PostgresWorldRepository",
    "CharacterRepository",
    "InMemoryCharacterRepository",
    "PostgresCharacterRepository",
    "SessionRepository",
    "InMemorySessionRepository",
    "PostgresSessionRepository",
    "EventRepository",
    "InMemoryEventRepository",
    "PostgresEventRepository",
]


def __getattr__(name: str):
    if name == "PostgresStore":
        from aether.repositories.store import PostgresStore

        return PostgresStore
    if name in {
        "PostgresWorldRepository",
        "PostgresCharacterRepository",
        "PostgresSessionRepository",
        "PostgresEventRepository",
    }:
        from aether.repositories import postgres as postgres_module

        return getattr(postgres_module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
