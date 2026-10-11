from __future__ import annotations

from abc import ABC, abstractmethod

from aether.domain.character import Character
from aether.repositories.base import NotFoundError


class CharacterRepository(ABC):
    """
    Persistence port for Character aggregates.

    Characters are scoped to a world.
    """

    @abstractmethod
    def get(self, world_id: str, character_id: str) -> Character:
        ...

    @abstractmethod
    def save(self, world_id: str, character: Character) -> Character:
        ...

    @abstractmethod
    def delete(self, world_id: str, character_id: str) -> None:
        ...

    @abstractmethod
    def exists(self, world_id: str, character_id: str) -> bool:
        ...

    @abstractmethod
    def list_by_world(self, world_id: str) -> list[Character]:
        ...


class InMemoryCharacterRepository(CharacterRepository):
    """Process-local Character store keyed by (world_id, character_id)."""

    def __init__(self) -> None:
        self._characters: dict[tuple[str, str], Character] = {}

    def get(self, world_id: str, character_id: str) -> Character:
        character = self._characters.get((world_id, character_id))
        if character is None:
            raise NotFoundError(
                f"Character not found: {character_id} in world {world_id}"
            )
        return character

    def save(self, world_id: str, character: Character) -> Character:
        self._characters[(world_id, character.id)] = character
        return character

    def delete(self, world_id: str, character_id: str) -> None:
        self._characters.pop((world_id, character_id), None)

    def exists(self, world_id: str, character_id: str) -> bool:
        return (world_id, character_id) in self._characters

    def list_by_world(self, world_id: str) -> list[Character]:
        return [
            character
            for (stored_world_id, _), character in self._characters.items()
            if stored_world_id == world_id
        ]
