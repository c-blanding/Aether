from __future__ import annotations

from abc import ABC, abstractmethod

from aether.domain.sessions import Session
from aether.repositories.base import NotFoundError


class SessionRepository(ABC):
    """Persistence port for Session aggregates."""

    @abstractmethod
    def get(self, session_id: str) -> Session:
        ...

    @abstractmethod
    def save(self, session: Session) -> Session:
        ...

    @abstractmethod
    def delete(self, session_id: str) -> None:
        ...

    @abstractmethod
    def exists(self, session_id: str) -> bool:
        ...

    @abstractmethod
    def list_by_world(self, world_id: str) -> list[Session]:
        ...


class InMemorySessionRepository(SessionRepository):
    """Process-local Session store."""

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            raise NotFoundError(f"Session not found: {session_id}")
        return session

    def save(self, session: Session) -> Session:
        self._sessions[session.id] = session
        return session

    def delete(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def exists(self, session_id: str) -> bool:
        return session_id in self._sessions

    def list_by_world(self, world_id: str) -> list[Session]:
        return [
            session
            for session in self._sessions.values()
            if session.world_id == world_id
        ]
