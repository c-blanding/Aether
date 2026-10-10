from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aether.domain.actions import Action
from aether.domain.events import WorldEvent
from aether.components.shared import new_id, utc_now


class InteractionStatus(str, Enum):
    """
    Lifecycle status for an interaction.
    """

    CREATED = "created"
    RUNNING = "running"
    COMMITTED = "committed"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationMode(str, Enum):
    """
    Desired generation style for an interaction response.
    """

    STRUCTURED = "structured"
    DIALOGUE = "dialogue"
    NARRATIVE = "narrative"
    CINEMATIC = "cinematic"


class InteractionRequest(BaseModel):
    """
    Raw request that started an interaction.
    """

    message: Optional[str] = Field(
        default=None,
        description="Natural-language message sent by the player, NPC, or system.",
    )

    actor_id: str = Field(
        default="player",
        description="ID of the actor who initiated this interaction.",
    )

    idempotency_key: Optional[str] = Field(
        default=None,
        description="Optional client-provided idempotency key for safe retries.",
    )

    generation_mode: GenerationMode = Field(
        default=GenerationMode.STRUCTURED,
        description="Requested response generation mode.",
    )


class Intent(BaseModel):
    """
    Interpreted intent for an interaction.
    """

    name: str = Field(
        ...,
        description="Name of the detected intent.",
        examples=["ask_question", "pick_up_item", "present_evidence"],
    )

    confidence: float = Field(
        default=1.0,
        description="Confidence score for the detected intent.",
        ge=0.0,
        le=1.0,
    )

    notes: Optional[str] = Field(
        default=None,
        description="Optional explanation or debugging notes for the intent.",
    )


class DialogueLine(BaseModel):
    """
    A generated line of dialogue.
    """

    character_id: str = Field(
        ...,
        description="ID of the character speaking.",
    )

    text: str = Field(
        ...,
        description="Dialogue text spoken by the character.",
    )

    emotion: Optional[str] = Field(
        default=None,
        description="Emotion associated with this line.",
    )


class RuntimeTrace(BaseModel):
    """
    Debug trace for an interaction.
    """

    steps: List[str] = Field(
        default_factory=list,
        description="Human-readable runtime steps recorded during the interaction.",
    )

    model_calls: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Raw model call metadata for debugging and observability.",
    )

    def add_step(self, step: str) -> None:
        self.steps.append(step)


class InteractionResult(BaseModel):
    """
    Final result returned from an interaction.
    """

    interaction_id: str = Field(
        ...,
        description="ID of the interaction this result belongs to.",
    )

    status: InteractionStatus = Field(
        default=InteractionStatus.COMPLETED,
        description="Final status of the interaction.",
    )

    dialogue: List[DialogueLine] = Field(
        default_factory=list,
        description="Generated dialogue lines for presentation.",
    )

    narrative: Optional[str] = Field(
        default=None,
        description="Optional generated narrative text.",
    )

    events: List[WorldEvent] = Field(
        default_factory=list,
        description="World events produced during this interaction.",
    )

    generation_job_ids: List[str] = Field(
        default_factory=list,
        description="IDs of asynchronous generation jobs created by this interaction.",
    )


class Interaction(BaseModel):
    """
    One player, NPC, or system interaction inside a session.
    """

    id: str = Field(
        default_factory=lambda: new_id("int"),
        description="Unique identifier for this interaction.",
    )

    session_id: str = Field(
        ...,
        description="ID of the session this interaction belongs to.",
    )

    branch_id: str = Field(
        ...,
        description="ID of the branch this interaction belongs to.",
    )

    request: InteractionRequest = Field(
        ...,
        description="Original request that started this interaction.",
    )

    intent: Optional[Intent] = Field(
        default=None,
        description="Interpreted intent for the interaction, if available.",
    )

    actions: List[Action] = Field(
        default_factory=list,
        description="Structured actions proposed or executed during this interaction.",
    )

    events: List[WorldEvent] = Field(
        default_factory=list,
        description="World events produced during this interaction.",
    )

    result: Optional[InteractionResult] = Field(
        default=None,
        description="Final result of the interaction.",
    )

    trace: RuntimeTrace = Field(
        default_factory=RuntimeTrace,
        description="Runtime trace for debugging and observability.",
    )

    status: InteractionStatus = Field(
        default=InteractionStatus.CREATED,
        description="Current interaction lifecycle status.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this interaction was created.",
    )

    @classmethod
    def from_message(
        cls,
        session_id: str,
        branch_id: str,
        message: str,
        actor_id: str = "player",
        idempotency_key: Optional[str] = None,
    ) -> "Interaction":
        return cls(
            session_id=session_id,
            branch_id=branch_id,
            request=InteractionRequest(
                message=message,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
            ),
        )


class InteractionHistory(BaseModel):
    """
    Ordered interaction history for a session.
    """

    interactions: List[Interaction] = Field(
        default_factory=list,
        description="Interactions that have occurred in this session.",
    )

    def add(self, interaction: Interaction) -> None:
        self.interactions.append(interaction)

    def latest(self, limit: int = 10) -> List[Interaction]:
        return self.interactions[-limit:]