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

SPEAKING_EVENT_TYPES = frozenset({"dialogue_spoken", "question_asked"})


class SpeakParams(BaseModel):
    """Parameters for speaking to the room."""

    topic: str = Field(
        ...,
        description="What the speaker intends to say (topic or gist). Exact wording is generated later.",
    )


class SayToParams(BaseModel):
    """Parameters for addressing a specific character."""

    target_character_id: str = Field(
        ...,
        description="ID of the character being addressed.",
    )
    topic: str = Field(
        ...,
        description="What the speaker intends to say (topic or gist). Exact wording is generated later.",
    )


class AskQuestionParams(BaseModel):
    """Parameters for asking a character a question."""

    target_character_id: str = Field(
        ...,
        description="ID of the character being asked.",
    )
    topic: str = Field(
        ...,
        description="Topic or intent of the question. Exact wording is generated later.",
    )


class DialogueSpokenAttributes(BaseModel):
    """Attributes for dialogue_spoken events."""

    speaker_id: str = Field(..., description="ID of the speaking character.")
    listener_id: str | None = Field(
        default=None,
        description="ID of the addressed character, if any.",
    )
    topic: str = Field(..., description="Gist of what was said.")
    addressed_room: bool = Field(
        default=False,
        description="Whether the speech was addressed to the whole room.",
    )


class QuestionAskedAttributes(BaseModel):
    """Attributes for question_asked events."""

    speaker_id: str = Field(..., description="ID of the character asking.")
    listener_id: str = Field(..., description="ID of the character being asked.")
    topic: str = Field(..., description="Topic or intent of the question.")


class DialogueModule(AetherModule):
    """
    Dialogue / speaking mechanics.

    Commits speaking events; polished NL comes from generate_dialogue.
    """

    name = "dialogue"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        registry.actions.register(
            action_type="speak",
            module_name=self.name,
            parameter_model=SpeakParams,
            handler=self.speak,
        )
        registry.actions.register(
            action_type="say_to",
            module_name=self.name,
            parameter_model=SayToParams,
            handler=self.say_to,
        )
        registry.actions.register(
            action_type="ask_question",
            module_name=self.name,
            parameter_model=AskQuestionParams,
            handler=self.ask_question,
        )

        registry.events.register(
            event_type="dialogue_spoken",
            module_name=self.name,
            attribute_model=DialogueSpokenAttributes,
        )
        registry.events.register(
            event_type="question_asked",
            module_name=self.name,
            attribute_model=QuestionAskedAttributes,
        )

        registry.perceptions.register(
            event_type="dialogue_spoken",
            module_name=self.name,
            handler=self.perceive_dialogue_spoken,
        )
        registry.perceptions.register(
            event_type="question_asked",
            module_name=self.name,
            handler=self.perceive_question_asked,
        )

    def _require_colocated(
        self,
        world: World,
        actor_id: str,
        target_id: str | None,
    ) -> None:
        actor = world.characters.get(actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {actor_id}")
        if actor.state.location_id is None:
            raise AetherValidationError("Actor has no current location.")
        if target_id is None:
            return
        target = world.characters.get(target_id)
        if target is None:
            raise AetherValidationError(f"Target does not exist: {target_id}")
        if actor.state.location_id != target.state.location_id:
            raise AetherValidationError(
                "Actor and target are not in the same location."
            )

    def speak(self, world: World, action: Action) -> List[WorldEvent]:
        params = SpeakParams.model_validate(action.data.parameters)
        self._require_colocated(world, action.actor_id, None)

        event = WorldEvent(
            world_id=world.id,
            actor_id=action.actor_id,
            target_ids=[],
            data=WorldActionEvent(
                type="dialogue_spoken",
                module="dialogue",
                attributes={
                    "speaker_id": action.actor_id,
                    "listener_id": None,
                    "topic": params.topic,
                    "addressed_room": True,
                },
            ),
            witnessed_by=world.determine_witnesses(action.actor_id),
        )
        return [event]

    def say_to(self, world: World, action: Action) -> List[WorldEvent]:
        params = SayToParams.model_validate(action.data.parameters)
        self._require_colocated(
            world, action.actor_id, params.target_character_id
        )

        event = WorldEvent(
            world_id=world.id,
            actor_id=action.actor_id,
            target_ids=[params.target_character_id],
            data=WorldActionEvent(
                type="dialogue_spoken",
                module="dialogue",
                attributes={
                    "speaker_id": action.actor_id,
                    "listener_id": params.target_character_id,
                    "topic": params.topic,
                    "addressed_room": False,
                },
            ),
            witnessed_by=world.determine_witnesses(action.actor_id),
        )
        return [event]

    def ask_question(self, world: World, action: Action) -> List[WorldEvent]:
        params = AskQuestionParams.model_validate(action.data.parameters)
        self._require_colocated(
            world, action.actor_id, params.target_character_id
        )

        event = WorldEvent(
            world_id=world.id,
            actor_id=action.actor_id,
            target_ids=[params.target_character_id],
            data=WorldActionEvent(
                type="question_asked",
                module="dialogue",
                attributes={
                    "speaker_id": action.actor_id,
                    "listener_id": params.target_character_id,
                    "topic": params.topic,
                },
            ),
            witnessed_by=world.determine_witnesses(action.actor_id),
        )
        return [event]

    def perceive_dialogue_spoken(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = DialogueSpokenAttributes.model_validate(event.data.attributes)
        speaker_name = world.describe_character(attrs.speaker_id)
        listener_name = (
            world.describe_character(attrs.listener_id)
            if attrs.listener_id
            else None
        )
        location_ids = []
        speaker = world.characters.get(attrs.speaker_id)
        if speaker is not None and speaker.state.location_id:
            location_ids.append(speaker.state.location_id)

        if character_id == attrs.speaker_id:
            if listener_name:
                perspective = f"I spoke to {listener_name} about {attrs.topic}."
            else:
                perspective = f"I spoke about {attrs.topic}."
            importance = 0.65
            emotion = None
            emotional_weight = 0.2
        elif attrs.listener_id and character_id == attrs.listener_id:
            perspective = f"{speaker_name} spoke to me about {attrs.topic}."
            importance = 0.75
            emotion = "attention"
            emotional_weight = 0.35
        else:
            if listener_name:
                perspective = (
                    f"I heard {speaker_name} speak to {listener_name} "
                    f"about {attrs.topic}."
                )
            else:
                perspective = f"I heard {speaker_name} speak about {attrs.topic}."
            importance = 0.5
            emotion = None
            emotional_weight = 0.15

        summary = (
            f"{speaker_name} spoke about {attrs.topic}."
            if not listener_name
            else f"{speaker_name} spoke to {listener_name} about {attrs.topic}."
        )

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=summary,
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["dialogue", "dialogue_spoken", attrs.topic.lower()[:40]],
            participant_ids=[
                value
                for value in [attrs.speaker_id, attrs.listener_id]
                if value
            ],
            location_ids=location_ids,
        )

    def perceive_question_asked(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = QuestionAskedAttributes.model_validate(event.data.attributes)
        speaker_name = world.describe_character(attrs.speaker_id)
        listener_name = world.describe_character(attrs.listener_id)
        location_ids = []
        speaker = world.characters.get(attrs.speaker_id)
        if speaker is not None and speaker.state.location_id:
            location_ids.append(speaker.state.location_id)

        if character_id == attrs.speaker_id:
            perspective = f"I asked {listener_name} about {attrs.topic}."
            importance = 0.7
            emotion = "curiosity"
            emotional_weight = 0.3
        elif character_id == attrs.listener_id:
            perspective = f"{speaker_name} asked me about {attrs.topic}."
            importance = 0.85
            emotion = "unease"
            emotional_weight = 0.45
        else:
            perspective = (
                f"I heard {speaker_name} ask {listener_name} about {attrs.topic}."
            )
            importance = 0.55
            emotion = None
            emotional_weight = 0.2

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=(
                f"{speaker_name} asked {listener_name} about {attrs.topic}."
            ),
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["dialogue", "question_asked", attrs.topic.lower()[:40]],
            participant_ids=[attrs.speaker_id, attrs.listener_id],
            location_ids=location_ids,
        )
