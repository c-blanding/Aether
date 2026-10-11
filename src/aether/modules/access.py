from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from aether.cognition.perception import Perception
from aether.components.shared import AetherValidationError
from aether.domain.actions import Action
from aether.domain.events import WorldActionEvent, WorldEvent
from aether.domain.world import Passage, World
from aether.engine.registries import ModuleRegistry
from aether.modules.base import AetherModule


class PassageParams(BaseModel):
    passage_id: str = Field(..., description="ID of the passage to change.")


class PassageChangedAttributes(BaseModel):
    passage_id: str
    actor_id: str
    from_location_id: str
    to_location_id: str
    locked: bool
    is_open: bool


class AccessModule(AetherModule):
    """
    Doors and gates.

    lock / unlock use a key from inventory when the passage names one.
    open / close change whether a character can walk through.
    """

    name = "access"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        for action_type, handler in (
            ("lock", self.lock),
            ("unlock", self.unlock),
            ("open", self.open_passage),
            ("close", self.close_passage),
        ):
            registry.actions.register(
                action_type=action_type,
                module_name=self.name,
                parameter_model=PassageParams,
                handler=handler,
            )

        for event_type in (
            "passage_locked",
            "passage_unlocked",
            "passage_opened",
            "passage_closed",
        ):
            registry.events.register(
                event_type=event_type,
                module_name=self.name,
                attribute_model=PassageChangedAttributes,
            )
            registry.perceptions.register(
                event_type=event_type,
                module_name=self.name,
                handler=self.perceive_passage_changed,
            )

    def _require_passage(self, world: World, action: Action) -> tuple[Passage, str]:
        params = PassageParams.model_validate(action.data.parameters)
        actor = world.characters.get(action.actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")
        passage = world.passages.get(params.passage_id)
        if passage is None:
            raise AetherValidationError(f"Passage does not exist: {params.passage_id}")
        if actor.state.location_id not in {
            passage.from_location_id,
            passage.to_location_id,
        }:
            raise AetherValidationError("Actor is not at this passage.")
        return passage, actor.id

    def _require_key(self, world: World, actor_id: str, passage: Passage) -> None:
        if passage.key_item_id is None:
            return
        actor = world.characters[actor_id]
        if not actor.inventory.contains(passage.key_item_id):
            raise AetherValidationError("Actor does not have the key.")

    def _event(
        self,
        world: World,
        actor_id: str,
        passage: Passage,
        event_type: str,
    ) -> WorldEvent:
        return WorldEvent(
            world_id=world.id,
            actor_id=actor_id,
            target_ids=[passage.id],
            data=WorldActionEvent(
                type=event_type,
                module="access",
                attributes={
                    "passage_id": passage.id,
                    "actor_id": actor_id,
                    "from_location_id": passage.from_location_id,
                    "to_location_id": passage.to_location_id,
                    "locked": passage.locked,
                    "is_open": passage.is_open,
                },
            ),
            witnessed_by=world.determine_witnesses(actor_id),
        )

    def lock(self, world: World, action: Action) -> List[WorldEvent]:
        passage, actor_id = self._require_passage(world, action)
        self._require_key(world, actor_id, passage)
        if passage.locked:
            raise AetherValidationError("Passage is already locked.")
        passage.locked = True
        return [self._event(world, actor_id, passage, "passage_locked")]

    def unlock(self, world: World, action: Action) -> List[WorldEvent]:
        passage, actor_id = self._require_passage(world, action)
        self._require_key(world, actor_id, passage)
        if not passage.locked:
            raise AetherValidationError("Passage is not locked.")
        passage.locked = False
        return [self._event(world, actor_id, passage, "passage_unlocked")]

    def open_passage(self, world: World, action: Action) -> List[WorldEvent]:
        passage, actor_id = self._require_passage(world, action)
        if passage.locked:
            raise AetherValidationError("Passage is locked.")
        if passage.is_open:
            raise AetherValidationError("Passage is already open.")
        passage.is_open = True
        return [self._event(world, actor_id, passage, "passage_opened")]

    def close_passage(self, world: World, action: Action) -> List[WorldEvent]:
        passage, actor_id = self._require_passage(world, action)
        if not passage.is_open:
            raise AetherValidationError("Passage is already closed.")
        passage.is_open = False
        return [self._event(world, actor_id, passage, "passage_closed")]

    def perceive_passage_changed(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = PassageChangedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.actor_id)
        verb = {
            "passage_locked": "locked",
            "passage_unlocked": "unlocked",
            "passage_opened": "opened",
            "passage_closed": "closed",
        }.get(event.type, "changed")
        destination = world.describe_location(attrs.to_location_id)
        if character_id == attrs.actor_id:
            perspective = f"I {verb} the way to the {destination}."
            importance = 0.6
        else:
            perspective = f"I saw {actor_name} {verb} the way to the {destination}."
            importance = 0.45
        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} {verb} the way to the {destination}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=0.15,
            tags=["access", event.type],
            participant_ids=[attrs.actor_id],
            location_ids=[attrs.from_location_id, attrs.to_location_id],
        )
