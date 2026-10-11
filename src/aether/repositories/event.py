from __future__ import annotations

from abc import ABC, abstractmethod

from aether.domain.events import WorldEvent
from aether.repositories.base import DuplicateError, NotFoundError


class EventRepository(ABC):
    """
    Append-only persistence port for committed WorldEvents.

    Maps to an events table in a real database.
    Duplicate IDs must raise DuplicateError — events are immutable.
    """

    @abstractmethod
    def get(self, event_id: str) -> WorldEvent:
        ...

    @abstractmethod
    def append(self, event: WorldEvent) -> WorldEvent:
        ...

    @abstractmethod
    def append_many(self, events: list[WorldEvent]) -> list[WorldEvent]:
        ...

    @abstractmethod
    def list_by_world(self, world_id: str) -> list[WorldEvent]:
        ...

    @abstractmethod
    def list_by_session(self, session_id: str) -> list[WorldEvent]:
        ...

    @abstractmethod
    def latest_by_world(self, world_id: str, limit: int = 10) -> list[WorldEvent]:
        """Return the most recent events for a world (chronological order)."""
        ...

    @abstractmethod
    def delete_by_world(self, world_id: str) -> None:
        """Remove all events for a world (used when deleting the world)."""
        ...

    def exists(self, event_id: str) -> bool:
        try:
            self.get(event_id)
            return True
        except NotFoundError:
            return False


class InMemoryEventRepository(EventRepository):
    """Process-local append-only event store."""

    def __init__(self) -> None:
        self._events: dict[str, WorldEvent] = {}
        self._order: list[str] = []

    def get(self, event_id: str) -> WorldEvent:
        event = self._events.get(event_id)
        if event is None:
            raise NotFoundError(f"Event not found: {event_id}")
        return event

    def append(self, event: WorldEvent) -> WorldEvent:
        if event.id in self._events:
            raise DuplicateError(f"Event already exists: {event.id}")
        self._order.append(event.id)
        self._events[event.id] = event
        return event

    def append_many(self, events: list[WorldEvent]) -> list[WorldEvent]:
        return [self.append(event) for event in events]

    def list_by_world(self, world_id: str) -> list[WorldEvent]:
        return [
            self._events[event_id]
            for event_id in self._order
            if self._events[event_id].world_id == world_id
        ]

    def list_by_session(self, session_id: str) -> list[WorldEvent]:
        return [
            self._events[event_id]
            for event_id in self._order
            if self._events[event_id].session_id is not None
            and self._events[event_id].session_id == session_id
        ]

    def latest_by_world(self, world_id: str, limit: int = 10) -> list[WorldEvent]:
        return self.list_by_world(world_id)[-limit:]

    def delete_by_world(self, world_id: str) -> None:
        keep_ids = [
            event_id
            for event_id in self._order
            if self._events[event_id].world_id != world_id
        ]
        for event_id in list(self._order):
            if event_id not in keep_ids:
                self._events.pop(event_id, None)
        self._order = keep_ids
