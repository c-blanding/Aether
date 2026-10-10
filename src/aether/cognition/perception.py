from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


from aether import World, WorldEvent


class Perception(BaseModel):
    """
    Character-specific interpretation of a world event.
    """

    character_id: str = Field(
        ...,
        description="ID of the character perceiving the event.",
    )

    event_id: str = Field(
        ...,
        description="ID of the event being perceived.",
    )

    summary: str = Field(
        ...,
        description="Objective-ish summary of what the character perceived.",
    )

    perspective: str = Field(
        ...,
        description="Subjective interpretation from this character's point of view.",
    )

    importance: float = Field(
        default=0.5,
        description="Importance score of this perception.",
        ge=0.0,
        le=1.0,
    )

    emotional_weight: float = Field(
        default=0.0,
        description="Emotional intensity of this perception.",
        ge=0.0,
        le=1.0,
    )

    emotion: Optional[str] = Field(
        default=None,
        description="Primary emotion triggered by this perception.",
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Tags associated with this perception.",
    )

    participant_ids: List[str] = Field(
        default_factory=list,
        description="Characters involved in this perceived event.",
    )

    location_ids: List[str] = Field(
        default_factory=list,
        description="Locations involved in this perceived event.",
    )


from typing import Optional

from aether.cognition.perception import Perception


class PerceptionProcessor:
    """
    Converts world events into character-specific perceptions
    by routing to module-registered perception handlers.
    """

    def perceive_event(
        self,
        world: "World",
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        handler = world.engine.modules.perceptions.get(event.type)

        if handler is None:
            return self._generic_perception(
                world=world,
                character_id=character_id,
                event=event,
            )

        return handler(
            world,
            character_id,
            event,
        )

    def _generic_perception(
        self,
        world: "World",
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        actor_name = world.describe_character(event.actor_id)

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} caused {event.type}.",
            perspective=f"I observed {actor_name} cause {event.type}.",
            importance=0.25,
            emotional_weight=0.0,
            tags=[event.type],
            participant_ids=[
                value
                for value in [event.actor_id]
                if value
            ],
        )