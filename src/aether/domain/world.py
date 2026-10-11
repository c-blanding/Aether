from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aether.domain.actions import Action
from aether.domain.character import Character, CharacterIdentity
from aether.domain.events import EventStore, WorldEvent
from aether.domain.relationship import RelationshipDelta
from aether.modules.base import AetherModule
from aether.components.shared import AetherError, AetherValidationError, new_id
from aether.engine.runtime_engine import RuntimeEngine

if TYPE_CHECKING:
    from aether.domain.sessions import Session


class WorldMetadata(BaseModel):
    """
    Descriptive metadata for a world.
    """

    name: str = Field(
        ...,
        description="Display name of the world.",
        examples=["Blackwood Manor"],
    )

    description: str = Field(
        default="",
        description="Natural-language description of the world.",
    )


class Location(BaseModel):
    """
    A place inside a world.
    """

    id: str = Field(
        default_factory=lambda: new_id("loc"),
        description="Unique identifier for this location.",
    )

    name: str = Field(
        ...,
        description="Display name of the location.",
        examples=["Library"],
    )

    description: str = Field(
        default="",
        description="Natural-language description of the location.",
    )

    connected_location_ids: List[str] = Field(
        default_factory=list,
        description="Location IDs directly connected to this location.",
    )


class ItemState(BaseModel):
    """
    Mutable placement/ownership state for an item.
    """

    location_id: Optional[str] = Field(
        default=None,
        description="ID of the location containing this item, if it is placed in the world.",
    )

    owner_id: Optional[str] = Field(
        default=None,
        description="ID of the character who owns this item, if it is held.",
    )

    def is_owned(self) -> bool:
        return self.owner_id is not None

    def is_in_location(self) -> bool:
        return self.location_id is not None


class Item(BaseModel):
    """
    An object that can exist in a world, location, or character inventory.
    """

    id: str = Field(
        default_factory=lambda: new_id("item"),
        description="Unique identifier for this item.",
    )

    name: str = Field(
        ...,
        description="Display name of the item.",
        examples=["Old Key"],
    )

    description: str = Field(
        default="",
        description="Natural-language description of the item.",
    )

    hidden: bool = Field(
        default=False,
        description=(
            "If true, the item is not obvious until revealed "
            "(e.g. via search_location)."
        ),
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Optional tags for modules and retrieval (e.g. clue, key).",
    )

    state: ItemState = Field(
        default_factory=ItemState,
        description="Mutable item state, including location and owner.",
    )


class WorldState(BaseModel):
    """
    Mutable state for a world aggregate.
    """

    version: int = Field(
        default=0,
        description="Monotonic version incremented whenever the world commits events.",
        ge=0,
    )

    active_session_ids: List[str] = Field(
        default_factory=list,
        description="IDs of active sessions for this world.",
    )

    def increment_version(self) -> None:
        self.version += 1


class SimulationResult(BaseModel):
    """
    Result of attempting to apply an action to a world.
    """

    accepted: bool = Field(
        ...,
        description="Whether the action was accepted and committed.",
    )

    reason: Optional[str] = Field(
        default=None,
        description="Reason the action failed, if it was rejected.",
    )

    action_id: Optional[str] = Field(
        default=None,
        description="ID of the action this result belongs to.",
    )

    events: List[WorldEvent] = Field(
        default_factory=list,
        description="Committed events produced by the action.",
    )

    perception_count: int = Field(
        default=0,
        description="Perceptions created while encoding this step (via Aether.step).",
        ge=0,
    )

    memory_count: int = Field(
        default=0,
        description="Memories written while encoding this step (via Aether.step).",
        ge=0,
    )

    beliefs_formed: int = Field(
        default=0,
        description="Beliefs formed/reinforced while encoding this step (via Aether.step).",
        ge=0,
    )

    relationship_deltas: List[RelationshipDelta] = Field(
        default_factory=list,
        description="Relationship deltas applied by social outcomes this step.",
    )


class World(BaseModel):
    """
    Aggregate root representing a persistent interactive world.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(
        default_factory=lambda: new_id("world"),
        description="Unique identifier for this world.",
    )

    metadata: WorldMetadata = Field(
        ...,
        description="Descriptive metadata for this world.",
    )

    state: WorldState = Field(
        default_factory=WorldState,
        description="Mutable world state.",
    )

    locations: Dict[str, Location] = Field(
        default_factory=dict,
        description="Mapping of location ID to Location.",
    )

    characters: Dict[str, Character] = Field(
        default_factory=dict,
        description="Mapping of character ID to Character.",
    )

    items: Dict[str, Item] = Field(
        default_factory=dict,
        description="Mapping of item ID to Item.",
    )

    sessions: Dict[str, Session] = Field(
        default_factory=dict,
        description="Mapping of session ID to Session aggregate.",
    )

    events: EventStore = Field(
        default_factory=EventStore,
        description="Committed world event store.",
    )

    engine: RuntimeEngine = Field(
        default_factory=RuntimeEngine,
        description="Runtime engine for this world.",
    )

    def _require_engine(self) -> RuntimeEngine:
        if self.engine is None:
            raise AetherValidationError(
                "World has no runtime engine. Create it via Aether.create_world()."
            )
        return self.engine

 

    def create_location(
        self,
        name: str,
        description: str = "",
    ) -> Location:
        location = Location(
            name=name,
            description=description,
        )

        self.locations[location.id] = location
        return location

    def connect_locations(
        self,
        from_location_id: str,
        to_location_id: str,
        bidirectional: bool = True,
    ) -> None:
        from_location = self.locations.get(from_location_id)
        to_location = self.locations.get(to_location_id)

        if from_location is None:
            raise AetherValidationError(
                f"Location does not exist: {from_location_id}"
            )

        if to_location is None:
            raise AetherValidationError(
                f"Location does not exist: {to_location_id}"
            )

        if to_location_id not in from_location.connected_location_ids:
            from_location.connected_location_ids.append(to_location_id)

        if bidirectional and from_location_id not in to_location.connected_location_ids:
            to_location.connected_location_ids.append(from_location_id)

    def create_character(
        self,
        name: str,
        role: str = "",
        background: str = "",
        location_id: Optional[str] = None,
    ) -> Character:
        if location_id is not None and location_id not in self.locations:
            raise AetherValidationError(
                f"Location does not exist: {location_id}"
            )

        character = Character(
            identity=CharacterIdentity(
                name=name,
                role=role,
                background=background,
            )
        )

        character.state.location_id = location_id
        self.characters[character.id] = character
        return character

    def create_item(
        self,
        name: str,
        description: str = "",
        location_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        *,
        hidden: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Item:
        if location_id is not None and location_id not in self.locations:
            raise AetherValidationError(
                f"Location does not exist: {location_id}"
            )

        if owner_id is not None and owner_id not in self.characters:
            raise AetherValidationError(
                f"Owner character does not exist: {owner_id}"
            )

        if location_id is not None and owner_id is not None:
            raise AetherValidationError(
                "Item cannot have both a location and an owner."
            )

        item = Item(
            name=name,
            description=description,
            hidden=hidden,
            tags=list(tags or []),
            state=ItemState(
                location_id=location_id,
                owner_id=owner_id,
            ),
        )

        self.items[item.id] = item

        if owner_id is not None:
            self.characters[owner_id].inventory.add(item.id)

        return item

    def get_item(self, item_id: str) -> Item:
        return self.items.get(item_id)

    def get_character_items(self, character_id: str) -> List[Item]:
        return [item for item in self.items.values() if item.state.owner_id == character_id]

    def create_session(
        self,
        external_player_id: Optional[str] = None,
    ) -> Session:
        from aether.domain.sessions import Session

        session = Session(
            world_id=self.id,
            external_player_id=external_player_id,
        )

        self.sessions[session.id] = session
        self.state.active_session_ids.append(session.id)
        session.sync_tip(self)

        return session


    def step(self, action: Action) -> SimulationResult:
        try:
            events = self._require_engine().execute(self, action)
            return SimulationResult(
                accepted=True,
                action_id=action.id,
                events=events,
            )
        except AetherError as exc:
            return SimulationResult(
                accepted=False,
                reason=str(exc),
                action_id=action.id,
            )

    def describe_character(self, character_id: str | None) -> str:
        if not character_id:
            return "someone"
        character = self.characters.get(character_id)
        return character.name if character is not None else "someone"

    def describe_item(self, item_id: str | None) -> str:
        if not item_id:
            return "an item"
        item = self.items.get(item_id)
        return item.name if item is not None else "an item"

    def describe_location(self, location_id: str | None) -> str:
        if not location_id:
            return "somewhere"
        location = self.locations.get(location_id)
        return location.name if location is not None else "somewhere"

    def determine_witnesses(self, actor_id: str) -> List[str]:
        actor = self.characters.get(actor_id)

        if actor is None:
            return []

        actor_location = actor.state.location_id

        return [
            character.id
            for character in self.characters.values()
            if character.state.location_id == actor_location
        ]