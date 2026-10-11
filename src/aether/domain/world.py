from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Literal, Optional

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


class Passage(BaseModel):
    """A door or gate between two locations."""

    id: str = Field(
        default_factory=lambda: new_id("pass"),
        description="Unique identifier for this passage.",
    )
    from_location_id: str
    to_location_id: str
    locked: bool = False
    is_open: bool = True
    key_item_id: Optional[str] = None
    bidirectional: bool = True

    def links(self, left_id: str, right_id: str) -> bool:
        pair = {left_id, right_id}
        endpoints = {self.from_location_id, self.to_location_id}
        if self.bidirectional:
            return pair == endpoints
        return left_id == self.from_location_id and right_id == self.to_location_id


class WorldClock(BaseModel):
    """Simple in-world clock advanced by the time module."""

    minute_of_day: int = Field(default=8 * 60, ge=0)
    day: int = Field(default=1, ge=1)

    def advance(self, minutes: int) -> None:
        if minutes < 0:
            raise AetherValidationError("Cannot advance the clock backwards.")
        total = self.minute_of_day + minutes
        self.day += total // (24 * 60)
        self.minute_of_day = total % (24 * 60)


class AgendaEntry(BaseModel):
    """Where a character is expected to be during a span of the day."""

    id: str = Field(default_factory=lambda: new_id("agenda"))
    character_id: str
    location_id: str
    start_minute: int = Field(ge=0, le=24 * 60)
    end_minute: int = Field(ge=0, le=24 * 60)

    def covers(self, minute_of_day: int) -> bool:
        if self.start_minute <= self.end_minute:
            return self.start_minute <= minute_of_day < self.end_minute
        return minute_of_day >= self.start_minute or minute_of_day < self.end_minute


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

    container_id: Optional[str] = Field(
        default=None,
        description="ID of the container item this item is inside, if any.",
    )

    consumed: bool = Field(
        default=False,
        description="Whether use_item has consumed this item.",
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

    is_container: bool = Field(
        default=False,
        description="Whether other items can be placed inside this item.",
    )

    container_open: bool = Field(
        default=False,
        description="Whether a container currently exposes its contents.",
    )

    use_mode: Literal["keep", "consume", "transform"] = Field(
        default="keep",
        description="What happens to the item when it is used.",
    )

    transform_name: Optional[str] = Field(
        default=None,
        description="Display name applied when use_mode is transform.",
    )

    transform_description: Optional[str] = Field(
        default=None,
        description="Description applied when use_mode is transform.",
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

    passages: Dict[str, Passage] = Field(
        default_factory=dict,
        description="Doors and gates between locations.",
    )

    clock: WorldClock = Field(
        default_factory=WorldClock,
        description="In-world clock advanced by wait.",
    )

    agendas: List[AgendaEntry] = Field(
        default_factory=list,
        description="Character schedules consulted when time passes.",
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
        container_id: Optional[str] = None,
        is_container: bool = False,
        container_open: bool = False,
        use_mode: Literal["keep", "consume", "transform"] = "keep",
        transform_name: Optional[str] = None,
        transform_description: Optional[str] = None,
    ) -> Item:
        if location_id is not None and location_id not in self.locations:
            raise AetherValidationError(
                f"Location does not exist: {location_id}"
            )

        if owner_id is not None and owner_id not in self.characters:
            raise AetherValidationError(
                f"Owner character does not exist: {owner_id}"
            )

        if container_id is not None:
            container = self.items.get(container_id)
            if container is None or not container.is_container:
                raise AetherValidationError(
                    f"Container does not exist: {container_id}"
                )

        placements = [
            value
            for value in (location_id, owner_id, container_id)
            if value is not None
        ]
        if len(placements) > 1:
            raise AetherValidationError(
                "Item cannot have more than one of location, owner, or container."
            )

        item = Item(
            name=name,
            description=description,
            hidden=hidden,
            tags=list(tags or []),
            is_container=is_container,
            container_open=container_open,
            use_mode=use_mode,
            transform_name=transform_name,
            transform_description=transform_description,
            state=ItemState(
                location_id=location_id,
                owner_id=owner_id,
                container_id=container_id,
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
        session.capture_baseline(self)

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

    def create_passage(
        self,
        from_location_id: str,
        to_location_id: str,
        *,
        locked: bool = False,
        is_open: bool = True,
        key_item_id: Optional[str] = None,
        bidirectional: bool = True,
    ) -> Passage:
        if from_location_id not in self.locations:
            raise AetherValidationError(
                f"Location does not exist: {from_location_id}"
            )
        if to_location_id not in self.locations:
            raise AetherValidationError(
                f"Location does not exist: {to_location_id}"
            )
        if key_item_id is not None and key_item_id not in self.items:
            raise AetherValidationError(f"Key item does not exist: {key_item_id}")

        self.connect_locations(
            from_location_id,
            to_location_id,
            bidirectional=bidirectional,
        )
        passage = Passage(
            from_location_id=from_location_id,
            to_location_id=to_location_id,
            locked=locked,
            is_open=is_open,
            key_item_id=key_item_id,
            bidirectional=bidirectional,
        )
        self.passages[passage.id] = passage
        return passage

    def passage_between(self, left_id: str, right_id: str) -> Optional[Passage]:
        for passage in self.passages.values():
            if passage.links(left_id, right_id):
                return passage
        return None

    def passage_block_reason(self, left_id: str, right_id: str) -> Optional[str]:
        passage = self.passage_between(left_id, right_id)
        if passage is None:
            return None
        if passage.locked:
            return "The way is locked."
        if not passage.is_open:
            return "The way is closed."
        return None

    def add_agenda(
        self,
        character_id: str,
        location_id: str,
        start_minute: int,
        end_minute: int,
    ) -> AgendaEntry:
        if character_id not in self.characters:
            raise AetherValidationError(f"Character does not exist: {character_id}")
        if location_id not in self.locations:
            raise AetherValidationError(f"Location does not exist: {location_id}")
        entry = AgendaEntry(
            character_id=character_id,
            location_id=location_id,
            start_minute=start_minute,
            end_minute=end_minute,
        )
        self.agendas.append(entry)
        return entry

    def active_agenda(self, character_id: str) -> Optional[AgendaEntry]:
        minute = self.clock.minute_of_day
        matches = [
            entry
            for entry in self.agendas
            if entry.character_id == character_id and entry.covers(minute)
        ]
        return matches[-1] if matches else None