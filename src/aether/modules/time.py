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


class WaitParams(BaseModel):
    minutes: int = Field(
        ...,
        ge=1,
        le=24 * 60,
        description="How many minutes pass.",
    )


class TimePassedAttributes(BaseModel):
    actor_id: str
    minutes: int
    minute_of_day: int
    day: int


class AgendaMovedAttributes(BaseModel):
    character_id: str
    previous_location_id: str | None = None
    new_location_id: str
    minute_of_day: int
    day: int


class TimeModule(AetherModule):
    """Advance the world clock and nudge characters onto their agendas."""

    name = "time"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        registry.actions.register(
            action_type="wait",
            module_name=self.name,
            parameter_model=WaitParams,
            handler=self.wait,
        )
        registry.events.register(
            event_type="time_passed",
            module_name=self.name,
            attribute_model=TimePassedAttributes,
        )
        registry.events.register(
            event_type="agenda_moved",
            module_name=self.name,
            attribute_model=AgendaMovedAttributes,
        )
        registry.perceptions.register(
            event_type="time_passed",
            module_name=self.name,
            handler=self.perceive_time_passed,
        )
        registry.perceptions.register(
            event_type="agenda_moved",
            module_name=self.name,
            handler=self.perceive_agenda_moved,
        )

    def wait(self, world: World, action: Action) -> List[WorldEvent]:
        params = WaitParams.model_validate(action.data.parameters)
        actor = world.characters.get(action.actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        world.clock.advance(params.minutes)
        events: List[WorldEvent] = [
            WorldEvent(
                world_id=world.id,
                actor_id=actor.id,
                target_ids=[],
                data=WorldActionEvent(
                    type="time_passed",
                    module="time",
                    attributes={
                        "actor_id": actor.id,
                        "minutes": params.minutes,
                        "minute_of_day": world.clock.minute_of_day,
                        "day": world.clock.day,
                    },
                ),
                witnessed_by=world.determine_witnesses(actor.id),
            )
        ]

        for character in list(world.characters.values()):
            agenda = world.active_agenda(character.id)
            if agenda is None or character.state.location_id == agenda.location_id:
                continue
            if (
                character.state.location_id is not None
                and world.passage_block_reason(
                    character.state.location_id,
                    agenda.location_id,
                )
            ):
                continue
            previous = character.state.location_id
            departure = (
                world.determine_witnesses(character.id) if previous is not None else []
            )
            character.state.location_id = agenda.location_id
            arrival = world.determine_witnesses(character.id)
            events.append(
                WorldEvent(
                    world_id=world.id,
                    actor_id=character.id,
                    target_ids=[agenda.location_id],
                    data=WorldActionEvent(
                        type="agenda_moved",
                        module="time",
                        attributes={
                            "character_id": character.id,
                            "previous_location_id": previous,
                            "new_location_id": agenda.location_id,
                            "minute_of_day": world.clock.minute_of_day,
                            "day": world.clock.day,
                        },
                    ),
                    witnessed_by=list(dict.fromkeys([*departure, *arrival])),
                )
            )
        return events

    def perceive_time_passed(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = TimePassedAttributes.model_validate(event.data.attributes)
        if character_id == attrs.actor_id:
            perspective = f"I waited {attrs.minutes} minutes."
        else:
            perspective = f"About {attrs.minutes} minutes passed."
        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{attrs.minutes} minutes passed.",
            perspective=perspective,
            importance=0.25,
            tags=["time", "time_passed"],
            participant_ids=[attrs.actor_id],
        )

    def perceive_agenda_moved(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = AgendaMovedAttributes.model_validate(event.data.attributes)
        name = world.describe_character(attrs.character_id)
        place = world.describe_location(attrs.new_location_id)
        if character_id == attrs.character_id:
            perspective = f"I went to the {place} as planned."
            importance = 0.5
        else:
            perspective = f"I noticed {name} go to the {place}."
            importance = 0.4
        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{name} went to the {place}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=0.1,
            tags=["time", "agenda_moved"],
            participant_ids=[attrs.character_id],
            location_ids=[
                value
                for value in [attrs.previous_location_id, attrs.new_location_id]
                if value
            ],
        )
