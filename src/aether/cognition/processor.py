from typing import Optional
from aether import World, WorldEvent
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