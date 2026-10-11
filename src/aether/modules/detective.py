from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from aether.cognition.perception import Perception
from aether.components.shared import AetherValidationError
from aether.domain.actions import Action
from aether.domain.events import WorldActionEvent, WorldEvent
from aether.domain.world import World
from aether.engine.registries import ModuleRegistry
from aether.modules.base import AetherModule


class ExamineParams(BaseModel):
    """Examine an item or location closely."""

    item_id: Optional[str] = Field(
        default=None,
        description="Item ID to examine. Mutually exclusive with location_id.",
    )
    location_id: Optional[str] = Field(
        default=None,
        description="Location ID to examine. Mutually exclusive with item_id.",
    )


class SearchLocationParams(BaseModel):
    """Search a location for hidden or overlooked items."""

    location_id: Optional[str] = Field(
        default=None,
        description=(
            "Location to search. Defaults to the actor's current location."
        ),
    )


class PresentEvidenceParams(BaseModel):
    """Show an owned item to another character without transferring ownership."""

    item_id: str = Field(..., description="ID of the item being presented.")
    target_character_id: str = Field(
        ...,
        description="ID of the character receiving the presentation.",
    )


class ExaminedAttributes(BaseModel):
    actor_id: str
    item_id: Optional[str] = None
    location_id: Optional[str] = None
    findings: str = ""


class LocationSearchedAttributes(BaseModel):
    actor_id: str
    location_id: str
    found_item_ids: List[str] = Field(default_factory=list)


class EvidencePresentedAttributes(BaseModel):
    actor_id: str
    item_id: str
    target_character_id: str


class DetectiveModule(AetherModule):
    """
    Observation / investigation verbs for interactive hosts.

    Horizontal enough for many apps; named detective for the common
    examine / search / present-evidence pattern.
    """

    name = "detective"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        registry.actions.register(
            action_type="examine",
            module_name=self.name,
            parameter_model=ExamineParams,
            handler=self.examine,
        )
        registry.actions.register(
            action_type="search_location",
            module_name=self.name,
            parameter_model=SearchLocationParams,
            handler=self.search_location,
        )
        registry.actions.register(
            action_type="present_evidence",
            module_name=self.name,
            parameter_model=PresentEvidenceParams,
            handler=self.present_evidence,
        )

        registry.events.register(
            event_type="examined",
            module_name=self.name,
            attribute_model=ExaminedAttributes,
        )
        registry.events.register(
            event_type="location_searched",
            module_name=self.name,
            attribute_model=LocationSearchedAttributes,
        )
        registry.events.register(
            event_type="evidence_presented",
            module_name=self.name,
            attribute_model=EvidencePresentedAttributes,
        )

        registry.perceptions.register(
            event_type="examined",
            module_name=self.name,
            handler=self.perceive_examined,
        )
        registry.perceptions.register(
            event_type="location_searched",
            module_name=self.name,
            handler=self.perceive_location_searched,
        )
        registry.perceptions.register(
            event_type="evidence_presented",
            module_name=self.name,
            handler=self.perceive_evidence_presented,
        )

    def examine(self, world: World, action: Action) -> List[WorldEvent]:
        params = ExamineParams.model_validate(action.data.parameters)
        actor = world.characters.get(action.actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        if bool(params.item_id) == bool(params.location_id):
            raise AetherValidationError(
                "Provide exactly one of item_id or location_id."
            )

        target_ids: list[str] = []
        findings = ""
        item_id = params.item_id
        location_id = params.location_id

        if item_id:
            item = world.items.get(item_id)
            if item is None:
                raise AetherValidationError(f"Item does not exist: {item_id}")
            if getattr(item, "hidden", False):
                raise AetherValidationError(
                    "Item is hidden; search the location first."
                )
            same_place = item.state.location_id == actor.state.location_id
            owned = item.state.owner_id == actor.id
            if not same_place and not owned:
                raise AetherValidationError(
                    "Item is not in the actor's location or inventory."
                )
            findings = item.description or f"A closer look at the {item.name}."
            target_ids = [item.id]
        else:
            assert location_id is not None
            location = world.locations.get(location_id)
            if location is None:
                raise AetherValidationError(
                    f"Location does not exist: {location_id}"
                )
            if actor.state.location_id != location_id:
                raise AetherValidationError(
                    "Actor must be in the location being examined."
                )
            findings = location.description or f"A survey of the {location.name}."
            target_ids = [location_id]

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=target_ids,
            data=WorldActionEvent(
                type="examined",
                module="detective",
                attributes={
                    "actor_id": actor.id,
                    "item_id": item_id,
                    "location_id": location_id
                    if location_id
                    else actor.state.location_id,
                    "findings": findings,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )
        return [event]

    def search_location(self, world: World, action: Action) -> List[WorldEvent]:
        params = SearchLocationParams.model_validate(action.data.parameters)
        actor = world.characters.get(action.actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        location_id = params.location_id or actor.state.location_id
        if location_id is None:
            raise AetherValidationError("Actor has no current location.")
        location = world.locations.get(location_id)
        if location is None:
            raise AetherValidationError(f"Location does not exist: {location_id}")
        if actor.state.location_id != location_id:
            raise AetherValidationError(
                "Actor must be in the location being searched."
            )

        found_item_ids: list[str] = []
        for item in world.items.values():
            if item.state.location_id != location_id:
                continue
            if getattr(item, "hidden", False):
                item.hidden = False
                found_item_ids.append(item.id)

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[location_id, *found_item_ids],
            data=WorldActionEvent(
                type="location_searched",
                module="detective",
                attributes={
                    "actor_id": actor.id,
                    "location_id": location_id,
                    "found_item_ids": found_item_ids,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )
        return [event]

    def present_evidence(self, world: World, action: Action) -> List[WorldEvent]:
        params = PresentEvidenceParams.model_validate(action.data.parameters)
        actor = world.characters.get(action.actor_id)
        target = world.characters.get(params.target_character_id)
        item = world.items.get(params.item_id)

        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")
        if target is None:
            raise AetherValidationError(
                f"Target does not exist: {params.target_character_id}"
            )
        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")
        if item.state.owner_id != actor.id:
            raise AetherValidationError("Actor does not own this item.")
        if actor.state.location_id != target.state.location_id:
            raise AetherValidationError(
                "Actor and target are not in the same location."
            )

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[target.id, item.id],
            data=WorldActionEvent(
                type="evidence_presented",
                module="detective",
                attributes={
                    "actor_id": actor.id,
                    "item_id": item.id,
                    "target_character_id": target.id,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )
        return [event]

    def perceive_examined(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ExaminedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.actor_id)
        if attrs.item_id:
            subject = world.describe_item(attrs.item_id)
            kind = "item"
        else:
            subject = world.describe_location(attrs.location_id)
            kind = "location"

        if character_id == attrs.actor_id:
            perspective = f"I examined the {subject}. {attrs.findings}".strip()
            importance = 0.7
            emotion = "focus"
            emotional_weight = 0.3
        else:
            perspective = f"I saw {actor_name} examine the {subject}."
            importance = 0.4
            emotion = None
            emotional_weight = 0.1

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} examined the {subject}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["detective", "examined", kind, subject.lower()],
            participant_ids=[attrs.actor_id],
            location_ids=[
                location_id
                for location_id in [attrs.location_id]
                if location_id
            ],
        )

    def perceive_location_searched(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = LocationSearchedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.actor_id)
        location_name = world.describe_location(attrs.location_id)
        found_names = [
            world.describe_item(item_id) for item_id in attrs.found_item_ids
        ]
        found_text = (
            f" Found: {', '.join(found_names)}."
            if found_names
            else " Nothing new turned up."
        )

        if character_id == attrs.actor_id:
            perspective = f"I searched the {location_name}.{found_text}"
            importance = 0.8 if attrs.found_item_ids else 0.55
            emotion = "curiosity" if attrs.found_item_ids else None
            emotional_weight = 0.4 if attrs.found_item_ids else 0.15
        else:
            perspective = f"I saw {actor_name} search the {location_name}.{found_text}"
            importance = 0.55 if attrs.found_item_ids else 0.35
            emotion = "unease" if attrs.found_item_ids else None
            emotional_weight = 0.25 if attrs.found_item_ids else 0.05

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} searched the {location_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["detective", "location_searched", location_name.lower()],
            participant_ids=[attrs.actor_id],
            location_ids=[attrs.location_id],
        )

    def perceive_evidence_presented(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = EvidencePresentedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.actor_id)
        target_name = world.describe_character(attrs.target_character_id)
        item_name = world.describe_item(attrs.item_id)

        if character_id == attrs.actor_id:
            perspective = f"I presented the {item_name} to {target_name}."
            importance = 0.8
            emotion = "resolve"
            emotional_weight = 0.4
        elif character_id == attrs.target_character_id:
            perspective = f"{actor_name} presented the {item_name} to me."
            importance = 0.9
            emotion = "alarm"
            emotional_weight = 0.55
        else:
            perspective = (
                f"I saw {actor_name} present the {item_name} to {target_name}."
            )
            importance = 0.6
            emotion = None
            emotional_weight = 0.2

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=(
                f"{actor_name} presented the {item_name} to {target_name}."
            ),
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["detective", "evidence_presented", item_name.lower()],
            participant_ids=[attrs.actor_id, attrs.target_character_id],
            location_ids=[],
        )
