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


class MoveParams(BaseModel):
    """Parameters for the move action."""

    destination_location_id: str = Field(
        ...,
        description="ID of the location the actor is moving to.",
    )


class CharacterMovedAttributes(BaseModel):
    """Attributes for the character_moved event."""

    character_id: str = Field(
        ...,
        description="ID of the character that moved.",
    )
    previous_location_id: str | None = Field(
        default=None,
        description="Location ID before the move.",
    )
    new_location_id: str = Field(
        ...,
        description="Location ID after the move.",
    )


class NavigationModule(AetherModule):
    """
    Navigation mechanics module.

    Adds support for:
    - move
    """

    name = "navigation"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        registry.actions.register(
            action_type="move",
            module_name=self.name,
            parameter_model=MoveParams,
            handler=self.move,
        )
        registry.events.register(
            event_type="character_moved",
            module_name=self.name,
            attribute_model=CharacterMovedAttributes,
        )
        registry.perceptions.register(
            event_type="character_moved",
            module_name=self.name,
            handler=self.perceive_character_moved,
        )

    def move(self, world: World, action: Action) -> List[WorldEvent]:
        params = MoveParams.model_validate(action.data.parameters)

        actor = world.characters.get(action.actor_id)
        destination = world.locations.get(params.destination_location_id)

        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        if destination is None:
            raise AetherValidationError(
                f"Destination does not exist: {params.destination_location_id}"
            )

        previous_location_id = actor.state.location_id
        if previous_location_id is None:
            raise AetherValidationError("Actor has no current location.")

        previous_location = world.locations.get(previous_location_id)
        if previous_location is None:
            raise AetherValidationError(
                f"Current location does not exist: {previous_location_id}"
            )

        if params.destination_location_id == previous_location_id:
            raise AetherValidationError("Actor is already at that location.")

        if params.destination_location_id not in previous_location.connected_location_ids:
            raise AetherValidationError(
                "Destination is not connected to the actor's current location."
            )

        blocked = world.passage_block_reason(
            previous_location_id,
            params.destination_location_id,
        )
        if blocked:
            raise AetherValidationError(blocked)

        # Witnesses at the departure room (before the move).
        departure_witnesses = world.determine_witnesses(actor.id)

        actor.state.location_id = params.destination_location_id

        arrival_witnesses = world.determine_witnesses(actor.id)
        witnessed_by = list(
            dict.fromkeys([*departure_witnesses, *arrival_witnesses])
        )

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[params.destination_location_id],
            data=WorldActionEvent(
                type="character_moved",
                module="navigation",
                attributes={
                    "character_id": actor.id,
                    "previous_location_id": previous_location_id,
                    "new_location_id": params.destination_location_id,
                },
            ),
            witnessed_by=witnessed_by,
        )
        return [event]

    def perceive_character_moved(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = CharacterMovedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.character_id)
        from_name = world.describe_location(attrs.previous_location_id)
        to_name = world.describe_location(attrs.new_location_id)

        if character_id == attrs.character_id:
            perspective = f"I moved from the {from_name} to the {to_name}."
            importance = 0.55
            emotion = None
            emotional_weight = 0.1
        else:
            # Witness may be in departure or arrival room.
            witness = world.characters.get(character_id)
            witness_location = (
                witness.state.location_id if witness is not None else None
            )
            if witness_location == attrs.new_location_id:
                perspective = f"I saw {actor_name} arrive in the {to_name}."
            else:
                perspective = f"I saw {actor_name} leave the {from_name}."
            importance = 0.4
            emotion = None
            emotional_weight = 0.05

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} moved from the {from_name} to the {to_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["navigation", "character_moved", to_name.lower()],
            participant_ids=[attrs.character_id],
            location_ids=[
                location_id
                for location_id in [
                    attrs.previous_location_id,
                    attrs.new_location_id,
                ]
                if location_id
            ],
        )
