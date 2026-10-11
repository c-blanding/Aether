from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from aether.cognition.knowledge import Belief
from aether.cognition.memory import MemoryRecord
from aether.cognition.perception import Perception, PerceptionProcessor

if TYPE_CHECKING:
    from aether.domain.events import WorldEvent
    from aether.domain.world import World


@dataclass
class CognitiveResult:
    """Outcome of encoding one or more events into character minds."""

    memories: list[MemoryRecord] = field(default_factory=list)
    beliefs: list[Belief] = field(default_factory=list)
    perceptions: list[Perception] = field(default_factory=list)


class CognitiveEngine:
    """
    Character cognition service.

    Turns committed world events into subjective perceptions, memories,
    and beliefs. Does not decide action success — RuntimeEngine owns that.
    """

    # Perceptions below this importance do not become durable beliefs.
    BELIEF_IMPORTANCE_THRESHOLD = 0.4

    def __init__(self, perception: PerceptionProcessor | None = None) -> None:
        self.perception = perception or PerceptionProcessor()

    def perceive_event(
        self,
        world: World,
        event: WorldEvent,
    ) -> list[Perception]:
        """Build a perception for each witness of the event."""
        perceptions: list[Perception] = []

        for character_id in event.witnessed_by:
            if character_id not in world.characters:
                continue

            perception = self.perception.perceive_event(
                world=world,
                character_id=character_id,
                event=event,
            )
            if perception is not None:
                perceptions.append(perception)

        return perceptions

    def remember_perception(
        self,
        world: World,
        perception: Perception,
    ) -> MemoryRecord | None:
        """Write one perception into the character's memory systems."""
        character = world.characters.get(perception.character_id)
        if character is None:
            return None

        memory = character.memory.remember(
            summary=perception.summary,
            perspective=perception.perspective,
            importance=perception.importance,
            emotional_weight=perception.emotional_weight,
            emotion=perception.emotion,
            source_event_ids=[perception.event_id],
            tags=perception.tags,
            participant_ids=perception.participant_ids,
            location_ids=perception.location_ids,
        )

        character.memory.add_working(
            text=perception.perspective,
            importance=perception.importance,
            source_event_ids=[perception.event_id],
        )

        if perception.emotion:
            character.state.emotion = perception.emotion

        return memory

    def learn_from_perception(
        self,
        world: World,
        perception: Perception,
    ) -> Belief | None:
        """
        Form or reinforce a belief from a meaningful perception.

        Uses the objective-ish summary as the proposition so beliefs stay
        shareable facts-from-that-character's-point-of-view.
        """
        if perception.importance < self.BELIEF_IMPORTANCE_THRESHOLD:
            return None

        character = world.characters.get(perception.character_id)
        if character is None:
            return None

        confidence = min(
            1.0,
            0.35 + (perception.importance * 0.45) + (perception.emotional_weight * 0.2),
        )

        return character.knowledge.learn(
            proposition=perception.summary,
            believed_value="true",
            confidence=confidence,
            source_event_ids=[perception.event_id],
        )

    def encode_perception(
        self,
        world: World,
        perception: Perception,
    ) -> tuple[MemoryRecord | None, Belief | None]:
        """Write memory and knowledge updates for one perception."""
        memory = self.remember_perception(world, perception)
        belief = self.learn_from_perception(world, perception)
        return memory, belief

    def encode_event(
        self,
        world: World,
        event: WorldEvent,
    ) -> CognitiveResult:
        """Perceive an event, then encode memory + knowledge for witnesses."""
        result = CognitiveResult()

        for perception in self.perceive_event(world, event):
            result.perceptions.append(perception)
            memory, belief = self.encode_perception(world, perception)
            if memory is not None:
                result.memories.append(memory)
            if belief is not None:
                result.beliefs.append(belief)

        return result

    def encode_events(
        self,
        world: World,
        events: list[WorldEvent],
    ) -> CognitiveResult:
        result = CognitiveResult()
        for event in events:
            encoded = self.encode_event(world, event)
            result.perceptions.extend(encoded.perceptions)
            result.memories.extend(encoded.memories)
            result.beliefs.extend(encoded.beliefs)
        return result
