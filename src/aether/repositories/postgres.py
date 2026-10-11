from __future__ import annotations

from typing import Any

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.types.json import Jsonb

from aether.domain.character import Character
from aether.domain.events import WorldEvent
from aether.domain.sessions import Session
from aether.domain.world import World
from aether.repositories.base import DuplicateError, NotFoundError
from aether.repositories.character import CharacterRepository
from aether.repositories.db import get_connection
from aether.repositories.event import EventRepository
from aether.repositories.serialization import (
    deserialize_character,
    deserialize_event,
    deserialize_session,
    deserialize_world,
    serialize_character,
    serialize_event,
    serialize_session,
    serialize_world,
)
from aether.repositories.session import SessionRepository
from aether.repositories.world import WorldRepository


def _as_jsonb(payload: dict[str, Any]) -> Jsonb:
    return Jsonb(payload)


class PostgresWorldRepository(WorldRepository):
    """Neon/Postgres-backed World repository (JSONB document storage)."""

    def __init__(self, conn: Connection | None = None) -> None:
        self._conn = conn

    def _connect(self):
        if self._conn is not None:
            return self._nullcontext(self._conn)
        return get_connection()

    @staticmethod
    def _nullcontext(conn: Connection):
        from contextlib import nullcontext

        return nullcontext(conn)

    def get(self, world_id: str) -> World:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM worlds WHERE id = %s",
                (world_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"World not found: {world_id}")
        return deserialize_world(row["data"])

    def save(self, world: World) -> World:
        payload = serialize_world(world)
        name = world.metadata.name
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO worlds (id, name, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET name = EXCLUDED.name,
                    data = EXCLUDED.data,
                    updated_at = now()
                """,
                (world.id, name, _as_jsonb(payload)),
            )
            if self._conn is None:
                conn.commit()
        return world

    def delete(self, world_id: str) -> None:
        """Idempotent: missing IDs are a no-op."""
        with self._connect() as conn:
            conn.execute("DELETE FROM worlds WHERE id = %s", (world_id,))
            if self._conn is None:
                conn.commit()

    def exists(self, world_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM worlds WHERE id = %s",
                (world_id,),
            ).fetchone()
        return row is not None

    def list(self) -> list[World]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT data FROM worlds ORDER BY created_at ASC"
            ).fetchall()
        return [deserialize_world(row["data"]) for row in rows]


class PostgresCharacterRepository(CharacterRepository):
    """Neon/Postgres-backed Character repository."""

    def __init__(self, conn: Connection | None = None) -> None:
        self._conn = conn

    def _connect(self):
        if self._conn is not None:
            from contextlib import nullcontext

            return nullcontext(self._conn)
        return get_connection()

    def get(self, world_id: str, character_id: str) -> Character:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT data FROM characters
                WHERE world_id = %s AND id = %s
                """,
                (world_id, character_id),
            ).fetchone()
        if row is None:
            raise NotFoundError(
                f"Character not found: {character_id} in world {world_id}"
            )
        return deserialize_character(row["data"])

    def save(self, world_id: str, character: Character) -> Character:
        payload = serialize_character(character)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO characters (id, world_id, name, data)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (world_id, id) DO UPDATE
                SET name = EXCLUDED.name,
                    data = EXCLUDED.data,
                    updated_at = now()
                """,
                (character.id, world_id, character.name, _as_jsonb(payload)),
            )
            if self._conn is None:
                conn.commit()
        return character

    def delete(self, world_id: str, character_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM characters WHERE world_id = %s AND id = %s",
                (world_id, character_id),
            )
            if self._conn is None:
                conn.commit()

    def exists(self, world_id: str, character_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM characters
                WHERE world_id = %s AND id = %s
                """,
                (world_id, character_id),
            ).fetchone()
        return row is not None

    def list_by_world(self, world_id: str) -> list[Character]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT data FROM characters
                WHERE world_id = %s
                ORDER BY created_at ASC
                """,
                (world_id,),
            ).fetchall()
        return [deserialize_character(row["data"]) for row in rows]


class PostgresSessionRepository(SessionRepository):
    """Neon/Postgres-backed Session repository."""

    def __init__(self, conn: Connection | None = None) -> None:
        self._conn = conn

    def _connect(self):
        if self._conn is not None:
            from contextlib import nullcontext

            return nullcontext(self._conn)
        return get_connection()

    def get(self, session_id: str) -> Session:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Session not found: {session_id}")
        return deserialize_session(row["data"])

    def save(self, session: Session) -> Session:
        payload = serialize_session(session)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, world_id, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO UPDATE
                SET world_id = EXCLUDED.world_id,
                    data = EXCLUDED.data,
                    updated_at = now()
                """,
                (session.id, session.world_id, _as_jsonb(payload)),
            )
            if self._conn is None:
                conn.commit()
        return session

    def delete(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM sessions WHERE id = %s", (session_id,))
            if self._conn is None:
                conn.commit()

    def exists(self, session_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE id = %s",
                (session_id,),
            ).fetchone()
        return row is not None

    def list_by_world(self, world_id: str) -> list[Session]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT data FROM sessions
                WHERE world_id = %s
                ORDER BY created_at ASC
                """,
                (world_id,),
            ).fetchall()
        return [deserialize_session(row["data"]) for row in rows]


class PostgresEventRepository(EventRepository):
    """Neon/Postgres append-only event repository."""

    def __init__(self, conn: Connection | None = None) -> None:
        self._conn = conn

    def _connect(self):
        if self._conn is not None:
            from contextlib import nullcontext

            return nullcontext(self._conn)
        return get_connection()

    def get(self, event_id: str) -> WorldEvent:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT data FROM events WHERE id = %s",
                (event_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Event not found: {event_id}")
        return deserialize_event(row["data"])

    def append(self, event: WorldEvent) -> WorldEvent:
        payload = serialize_event(event)
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO events (
                        id, world_id, session_id, event_type, actor_id, occurred_at, data
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event.id,
                        event.world_id,
                        event.session_id,
                        event.type,
                        event.actor_id,
                        event.occurred_at,
                        _as_jsonb(payload),
                    ),
                )
            except UniqueViolation as exc:
                raise DuplicateError(f"Event already exists: {event.id}") from exc
            if self._conn is None:
                conn.commit()
        return event

    def append_many(self, events: list[WorldEvent]) -> list[WorldEvent]:
        return [self.append(event) for event in events]

    def list_by_world(self, world_id: str) -> list[WorldEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT data FROM events
                WHERE world_id = %s
                ORDER BY occurred_at ASC, created_at ASC
                """,
                (world_id,),
            ).fetchall()
        return [deserialize_event(row["data"]) for row in rows]

    def list_by_session(self, session_id: str) -> list[WorldEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT data FROM events
                WHERE session_id = %s
                ORDER BY occurred_at ASC, created_at ASC
                """,
                (session_id,),
            ).fetchall()
        return [deserialize_event(row["data"]) for row in rows]

    def latest_by_world(self, world_id: str, limit: int = 10) -> list[WorldEvent]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT data FROM events
                WHERE world_id = %s
                ORDER BY occurred_at DESC, created_at DESC
                LIMIT %s
                """,
                (world_id, limit),
            ).fetchall()
        # Return chronological order (oldest -> newest)
        return [deserialize_event(row["data"]) for row in reversed(rows)]

    def delete_by_world(self, world_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM events WHERE world_id = %s", (world_id,))
            if self._conn is None:
                conn.commit()


def open_postgres_connection(database_url: str | None = None) -> Connection:
    """Open a single dict-row connection (useful for migrations / tests)."""
    import psycopg
    from psycopg.rows import dict_row

    from aether.repositories.db import get_database_url

    return psycopg.connect(
        database_url or get_database_url(),
        row_factory=dict_row,
    )
