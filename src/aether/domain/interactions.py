from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aether.domain.actions import Action
from aether.domain.events import WorldEvent
from aether.domain.presentation import SceneSummary
from aether.domain.relationship import RelationshipDelta
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

    character_name: str = Field(
        ...,
        description="Name of the character speaking.",
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

    reject_reasons: List[str] = Field(
        default_factory=list,
        description="Validation/execution rejection reasons collected this turn.",
    )

    def add_step(self, step: str) -> None:
        self.steps.append(step)

    def add_rejection(self, reason: str) -> None:
        if reason:
            self.reject_reasons.append(reason)


class OpenQuestion(BaseModel):
    """An asked question that no later answer or refusal has closed."""

    event_id: str = Field(..., description="ID of the question_asked event.")
    topic: str = Field(default="", description="Topic gist of the question.")
    speaker_id: str = Field(default="", description="Character who asked.")
    listener_ids: List[str] = Field(
        default_factory=list,
        description="Characters the question was addressed to.",
    )


def _topics_overlap(left: str, right: str) -> bool:
    a = (left or "").strip().lower()
    b = (right or "").strip().lower()
    if not a or not b:
        return True
    return a == b or a in b or b in a


def unanswered_questions(events: List[WorldEvent]) -> List[OpenQuestion]:
    """
    Questions still open on this event log.

    A later ``question_answered`` or ``dialogue_refused`` closes a matching ask.
    """
    open_items: List[OpenQuestion] = []
    for event in events:
        attrs = event.data.attributes or {}
        if event.type == "question_asked":
            open_items.append(
                OpenQuestion(
                    event_id=event.id,
                    topic=str(attrs.get("topic") or ""),
                    speaker_id=str(attrs.get("speaker_id") or event.actor_id or ""),
                    listener_ids=[
                        value
                        for value in (attrs.get("listener_ids") or [])
                        if isinstance(value, str)
                    ],
                )
            )
            continue
        if event.type not in {"question_answered", "dialogue_refused"}:
            continue

        topic = str(attrs.get("topic") or "")
        questioner_id = attrs.get("questioner_id")
        if questioner_id is None:
            open_items = [
                item
                for item in open_items
                if not _topics_overlap(item.topic, topic)
            ]
            continue

        remaining: List[OpenQuestion] = []
        closed = False
        for item in open_items:
            if (
                not closed
                and item.speaker_id == questioner_id
                and _topics_overlap(item.topic, topic)
            ):
                closed = True
                continue
            remaining.append(item)
        if not closed:
            remaining = []
            closed = False
            for item in open_items:
                if not closed and item.speaker_id == questioner_id:
                    closed = True
                    continue
                remaining.append(item)
        open_items = remaining
    return open_items


class TurnDecision(BaseModel):
    """One decide/execute beat recorded for host UI/debug."""

    kind: str = Field(
        ...,
        description="Decision kind: action, respond, continue, etc.",
    )
    action_type: Optional[str] = Field(default=None)
    actor_id: Optional[str] = Field(default=None)
    accepted: Optional[bool] = Field(default=None)
    rejection: Optional[str] = Field(default=None)
    source: Optional[str] = Field(
        default=None,
        description="Origin of the decision, e.g. player planner or npc_react.",
    )
    reason: Optional[str] = Field(default=None)


class TurnReport(BaseModel):
    """
    Stable host-facing summary of one interact() turn.
    """

    decisions: List[TurnDecision] = Field(default_factory=list)
    reject_reasons: List[str] = Field(default_factory=list)
    event_types: List[str] = Field(default_factory=list)
    speaking_event_types: List[str] = Field(default_factory=list)
    dialogue_line_count: int = Field(default=0, ge=0)
    npc_action_types: List[str] = Field(default_factory=list)
    perception_count: int = Field(default=0, ge=0)
    memory_count: int = Field(default=0, ge=0)
    beliefs_formed: int = Field(default=0, ge=0)
    scene_summary: Optional[SceneSummary] = Field(
        default=None,
        description="Scene continuity summary after this turn.",
    )
    relationship_deltas: List[RelationshipDelta] = Field(
        default_factory=list,
        description="Social relationship deltas applied during this turn.",
    )
    open_question_ids: List[str] = Field(
        default_factory=list,
        description="Event IDs of questions still unanswered after this turn.",
    )
    open_questions: List[OpenQuestion] = Field(
        default_factory=list,
        description="Unanswered questions (topic and asker) still in play.",
    )


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

    report: Optional[TurnReport] = Field(
        default=None,
        description="Structured turn report for host UI and debugging.",
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

    def by_ids(self, interaction_ids: set[str]) -> List[Interaction]:
        if not interaction_ids:
            return []
        return [
            interaction
            for interaction in self.interactions
            if interaction.id in interaction_ids
        ]

    def for_branch(self, branch_id: str) -> List[Interaction]:
        """Interactions tagged with a single branch id (no ancestry)."""
        return [
            interaction
            for interaction in self.interactions
            if interaction.branch_id == branch_id
        ]
