from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, model_validator

from aether.cognition.perception import Perception
from aether.components.shared import AetherValidationError
from aether.domain.actions import Action
from aether.domain.events import WorldActionEvent, WorldEvent
from aether.domain.world import World
from aether.engine.registries import ModuleRegistry
from aether.modules.base import AetherModule

SPEAKING_EVENT_TYPES = frozenset(
    {"dialogue_spoken", "question_asked", "question_answered"}
)


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
    """
    Parameters for asking a question.

    - Provide one or more ``target_character_ids`` to address specific people.
    - Leave ``target_character_ids`` empty to address the crowd
      (everyone else currently in the speaker's location).
    """

    topic: str = Field(
        ...,
        description="Topic or intent of the question. Exact wording is generated later.",
    )
    target_character_ids: List[str] = Field(
        default_factory=list,
        description=(
            "Character IDs being asked. Empty means address the crowd "
            "in the speaker's current location."
        ),
    )
    target_character_id: Optional[str] = Field(
        default=None,
        description="Optional single target (merged into target_character_ids).",
    )

    @model_validator(mode="after")
    def _merge_single_target(self) -> "AskQuestionParams":
        if self.target_character_id:
            if self.target_character_id not in self.target_character_ids:
                self.target_character_ids = [
                    *self.target_character_ids,
                    self.target_character_id,
                ]
        return self


class AnswerQuestionParams(BaseModel):
    """Parameters for answering a question."""

    topic: str = Field(
        ...,
        description="Topic or gist of the answer. Exact wording is generated later.",
    )
    questioner_id: Optional[str] = Field(
        default=None,
        description=(
            "ID of the character who asked, if answering someone specific. "
            "Omit to answer the room/crowd."
        ),
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
    listener_ids: List[str] = Field(
        default_factory=list,
        description="Character IDs being asked (one person, several, or the crowd).",
    )
    addressed_crowd: bool = Field(
        default=False,
        description="Whether the question was addressed to everyone present.",
    )
    topic: str = Field(..., description="Topic or intent of the question.")


class QuestionAnsweredAttributes(BaseModel):
    """Attributes for question_answered events."""

    speaker_id: str = Field(..., description="ID of the character answering.")
    questioner_id: str | None = Field(
        default=None,
        description="ID of the character who asked, if answering someone specific.",
    )
    listener_ids: List[str] = Field(
        default_factory=list,
        description="Character IDs intended to hear the answer.",
    )
    addressed_crowd: bool = Field(
        default=False,
        description="Whether the answer was given to the room/crowd.",
    )
    topic: str = Field(..., description="Topic or gist of the answer.")


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
        registry.actions.register(
            action_type="answer_question",
            module_name=self.name,
            parameter_model=AnswerQuestionParams,
            handler=self.answer_question,
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
        registry.events.register(
            event_type="question_answered",
            module_name=self.name,
            attribute_model=QuestionAnsweredAttributes,
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
        registry.perceptions.register(
            event_type="question_answered",
            module_name=self.name,
            handler=self.perceive_question_answered,
        )

    def _require_actor_located(self, world: World, actor_id: str):
        actor = world.characters.get(actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {actor_id}")
        if actor.state.location_id is None:
            raise AetherValidationError("Actor has no current location.")
        return actor

    def _require_colocated(
        self,
        world: World,
        actor_id: str,
        target_id: str | None,
    ) -> None:
        self._require_actor_located(world, actor_id)
        if target_id is None:
            return
        target = world.characters.get(target_id)
        if target is None:
            raise AetherValidationError(f"Target does not exist: {target_id}")
        actor = world.characters[actor_id]
        if actor.state.location_id != target.state.location_id:
            raise AetherValidationError(
                "Actor and target are not in the same location."
            )

    def _require_colocated_many(
        self,
        world: World,
        actor_id: str,
        target_ids: list[str],
    ) -> None:
        actor = self._require_actor_located(world, actor_id)
        for target_id in target_ids:
            target = world.characters.get(target_id)
            if target is None:
                raise AetherValidationError(f"Target does not exist: {target_id}")
            if target_id == actor_id:
                raise AetherValidationError(
                    "Actor cannot target themselves as a listener."
                )
            if actor.state.location_id != target.state.location_id:
                raise AetherValidationError(
                    f"Actor and target are not in the same location: {target_id}"
                )

    def _crowd_at_location(
        self,
        world: World,
        actor_id: str,
    ) -> list[str]:
        actor = self._require_actor_located(world, actor_id)
        return [
            character.id
            for character in world.characters.values()
            if character.id != actor_id
            and character.state.location_id == actor.state.location_id
        ]

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

        if params.target_character_ids:
            listener_ids = list(dict.fromkeys(params.target_character_ids))
            addressed_crowd = False
            self._require_colocated_many(world, action.actor_id, listener_ids)
        else:
            listener_ids = self._crowd_at_location(world, action.actor_id)
            addressed_crowd = True
            if not listener_ids:
                raise AetherValidationError(
                    "No one else is present to ask; crowd is empty."
                )

        event = WorldEvent(
            world_id=world.id,
            actor_id=action.actor_id,
            target_ids=listener_ids,
            data=WorldActionEvent(
                type="question_asked",
                module="dialogue",
                attributes={
                    "speaker_id": action.actor_id,
                    "listener_ids": listener_ids,
                    "addressed_crowd": addressed_crowd,
                    "topic": params.topic,
                },
            ),
            witnessed_by=world.determine_witnesses(action.actor_id),
        )
        return [event]

    def answer_question(self, world: World, action: Action) -> List[WorldEvent]:
        params = AnswerQuestionParams.model_validate(action.data.parameters)
        self._require_actor_located(world, action.actor_id)

        if params.questioner_id:
            self._require_colocated(
                world, action.actor_id, params.questioner_id
            )
            listener_ids = [params.questioner_id]
            addressed_crowd = False
        else:
            listener_ids = self._crowd_at_location(world, action.actor_id)
            addressed_crowd = True

        event = WorldEvent(
            world_id=world.id,
            actor_id=action.actor_id,
            target_ids=listener_ids,
            data=WorldActionEvent(
                type="question_answered",
                module="dialogue",
                attributes={
                    "speaker_id": action.actor_id,
                    "questioner_id": params.questioner_id,
                    "listener_ids": listener_ids,
                    "addressed_crowd": addressed_crowd,
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
            topic_l = attrs.topic.lower()
            if any(
                token in topic_l
                for token in ("thank", "sorry", "friend", "welcome", "care")
            ):
                emotion = "warmth"
            elif any(
                token in topic_l
                for token in ("threat", "accuse", "suspect", "lie", "betray")
            ):
                emotion = "resentment"
            else:
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

    def _listener_names(self, world: World, listener_ids: list[str]) -> str:
        names = [world.describe_character(listener_id) for listener_id in listener_ids]
        if not names:
            return "the room"
        if len(names) == 1:
            return names[0]
        if len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names[:-1]) + f", and {names[-1]}"

    def perceive_question_asked(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = QuestionAskedAttributes.model_validate(event.data.attributes)
        speaker_name = world.describe_character(attrs.speaker_id)
        audience = (
            "everyone present"
            if attrs.addressed_crowd
            else self._listener_names(world, attrs.listener_ids)
        )
        location_ids = []
        speaker = world.characters.get(attrs.speaker_id)
        if speaker is not None and speaker.state.location_id:
            location_ids.append(speaker.state.location_id)

        if character_id == attrs.speaker_id:
            perspective = f"I asked {audience} about {attrs.topic}."
            importance = 0.7
            emotion = "curiosity"
            emotional_weight = 0.3
        elif character_id in attrs.listener_ids:
            if attrs.addressed_crowd and len(attrs.listener_ids) > 1:
                perspective = (
                    f"{speaker_name} asked the room about {attrs.topic}, "
                    "including me."
                )
            else:
                perspective = f"{speaker_name} asked me about {attrs.topic}."
            importance = 0.85
            emotion = "unease"
            emotional_weight = 0.45
        else:
            perspective = (
                f"I heard {speaker_name} ask {audience} about {attrs.topic}."
            )
            importance = 0.55
            emotion = None
            emotional_weight = 0.2

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{speaker_name} asked {audience} about {attrs.topic}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["dialogue", "question_asked", attrs.topic.lower()[:40]],
            participant_ids=[attrs.speaker_id, *attrs.listener_ids],
            location_ids=location_ids,
        )

    def perceive_question_answered(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = QuestionAnsweredAttributes.model_validate(event.data.attributes)
        speaker_name = world.describe_character(attrs.speaker_id)
        if attrs.addressed_crowd:
            audience = "the room"
        elif attrs.questioner_id:
            audience = world.describe_character(attrs.questioner_id)
        else:
            audience = self._listener_names(world, attrs.listener_ids)

        location_ids = []
        speaker = world.characters.get(attrs.speaker_id)
        if speaker is not None and speaker.state.location_id:
            location_ids.append(speaker.state.location_id)

        if character_id == attrs.speaker_id:
            perspective = f"I answered {audience} about {attrs.topic}."
            importance = 0.75
            emotion = "resolve"
            emotional_weight = 0.35
        elif attrs.questioner_id and character_id == attrs.questioner_id:
            perspective = f"{speaker_name} answered my question about {attrs.topic}."
            importance = 0.85
            emotion = "attention"
            emotional_weight = 0.4
        elif character_id in attrs.listener_ids:
            perspective = f"{speaker_name} answered about {attrs.topic}."
            importance = 0.65
            emotion = None
            emotional_weight = 0.2
        else:
            perspective = (
                f"I heard {speaker_name} answer {audience} about {attrs.topic}."
            )
            importance = 0.5
            emotion = None
            emotional_weight = 0.15

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{speaker_name} answered {audience} about {attrs.topic}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["dialogue", "question_answered", attrs.topic.lower()[:40]],
            participant_ids=[
                value
                for value in [attrs.speaker_id, attrs.questioner_id, *attrs.listener_ids]
                if value
            ],
            location_ids=location_ids,
        )
