from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List

from pydantic import BaseModel, Field

from aether.components.planner import Planner
from aether.domain.character import Character
from aether.domain.events import EventStore
from aether.domain.world import AgendaEntry, Item, Location, Passage, WorldClock, WorldState

if TYPE_CHECKING:
    from aether.domain.world import World


class WorldSnapshot(BaseModel):
    """
    Isolated copy of mutable world simulation state for a timeline branch.

    Excludes identity, metadata, sessions, and the runtime engine so applying
    a snapshot restores gameplay state without losing session wiring.
    """

    state: WorldState = Field(
        default_factory=WorldState,
        description="Mutable world aggregate state.",
    )

    locations: Dict[str, Location] = Field(
        default_factory=dict,
        description="Location map at snapshot time.",
    )

    characters: Dict[str, Character] = Field(
        default_factory=dict,
        description="Character map at snapshot time (including memory/knowledge).",
    )

    items: Dict[str, Item] = Field(
        default_factory=dict,
        description="Item map at snapshot time.",
    )

    events: EventStore = Field(
        default_factory=EventStore,
        description="Committed events visible on this branch tip.",
    )

    passages: Dict[str, Passage] = Field(
        default_factory=dict,
        description="Passages at snapshot time.",
    )

    clock: WorldClock = Field(
        default_factory=WorldClock,
        description="World clock at snapshot time.",
    )

    agendas: List[AgendaEntry] = Field(
        default_factory=list,
        description="Character agendas at snapshot time.",
    )

    @staticmethod
    def _clone_characters(
        characters: Dict[str, Character],
    ) -> Dict[str, Character]:
        cloned: Dict[str, Character] = {}
        for character_id, character in characters.items():
            data = character.model_dump(mode="python", exclude={"planner"})
            data["planner"] = Planner(
                strategy=getattr(character.planner, "strategy", "goal_driven")
            )
            cloned[character_id] = Character.model_validate(data)
        return cloned

    @classmethod
    def capture(cls, world: World) -> WorldSnapshot:
        """Deep-copy mutable simulation fields from a live world."""
        return cls(
            state=world.state.model_copy(deep=True),
            locations={
                location_id: location.model_copy(deep=True)
                for location_id, location in world.locations.items()
            },
            characters=cls._clone_characters(world.characters),
            items={
                item_id: item.model_copy(deep=True)
                for item_id, item in world.items.items()
            },
            events=world.events.model_copy(deep=True),
            passages={
                passage_id: passage.model_copy(deep=True)
                for passage_id, passage in world.passages.items()
            },
            clock=world.clock.model_copy(deep=True),
            agendas=[entry.model_copy(deep=True) for entry in world.agendas],
        )

    def clone(self) -> WorldSnapshot:
        """Independent deep copy of this snapshot."""
        return WorldSnapshot(
            state=self.state.model_copy(deep=True),
            locations={
                location_id: location.model_copy(deep=True)
                for location_id, location in self.locations.items()
            },
            characters=self._clone_characters(self.characters),
            items={
                item_id: item.model_copy(deep=True)
                for item_id, item in self.items.items()
            },
            events=self.events.model_copy(deep=True),
            passages={
                passage_id: passage.model_copy(deep=True)
                for passage_id, passage in self.passages.items()
            },
            clock=self.clock.model_copy(deep=True),
            agendas=[entry.model_copy(deep=True) for entry in self.agendas],
        )

    def apply_to(self, world: World) -> None:
        """
        Replace live world simulation state with this snapshot.

        Preserves ``world.id``, ``metadata``, ``sessions``, and ``engine``.
        Re-syncs ``active_session_ids`` from live sessions so session wiring
        is never rewound by an older tip.
        """
        world.state = self.state.model_copy(deep=True)
        world.state.active_session_ids = list(world.sessions.keys())
        world.locations = {
            location_id: location.model_copy(deep=True)
            for location_id, location in self.locations.items()
        }
        world.characters = self._clone_characters(self.characters)
        world.items = {
            item_id: item.model_copy(deep=True)
            for item_id, item in self.items.items()
        }
        world.events = self.events.model_copy(deep=True)
        world.passages = {
            passage_id: passage.model_copy(deep=True)
            for passage_id, passage in self.passages.items()
        }
        world.clock = self.clock.model_copy(deep=True)
        world.agendas = [entry.model_copy(deep=True) for entry in self.agendas]
