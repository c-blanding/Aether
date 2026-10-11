from __future__ import annotations

from abc import ABC

from aether.repositories.character import (
    CharacterRepository,
    InMemoryCharacterRepository,
)
from aether.repositories.event import EventRepository, InMemoryEventRepository
from aether.repositories.session import InMemorySessionRepository, SessionRepository
from aether.repositories.world import InMemoryWorldRepository, WorldRepository


class Store(ABC):
    """
    Persistence bundle for the Aether SDK.

    Host apps pick a store once; the SDK wires repositories internally.
    """

    worlds: WorldRepository
    events: EventRepository
    characters: CharacterRepository
    sessions: SessionRepository


class InMemoryStore(Store):
    """Default process-local store for demos and tests."""

    def __init__(self) -> None:
        self.worlds = InMemoryWorldRepository()
        self.events = InMemoryEventRepository()
        self.characters = InMemoryCharacterRepository()
        self.sessions = InMemorySessionRepository()


class PostgresStore(Store):
    """
    Neon/Postgres-backed store.

    Requires ``DATABASE_URL`` and ``psycopg``. Pass ``apply_migrations=True``
    to create tables on first use.
    """

    def __init__(self, *, apply_migrations: bool = False) -> None:
        from aether.repositories.db import apply_schema
        from aether.repositories.postgres import (
            PostgresCharacterRepository,
            PostgresEventRepository,
            PostgresSessionRepository,
            PostgresWorldRepository,
        )

        if apply_migrations:
            apply_schema()

        self.worlds = PostgresWorldRepository()
        self.events = PostgresEventRepository()
        self.characters = PostgresCharacterRepository()
        self.sessions = PostgresSessionRepository()
