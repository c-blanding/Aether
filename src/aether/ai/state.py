from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

import operator
from typing_extensions import TypedDict

from pydantic import BaseModel, Field


class NextStepDecision(BaseModel):
    """Structured LLM output for the act-one decide node."""

    kind: Literal["action", "respond"] = Field(
        ...,
        description=(
            "Choose 'action' to attempt one registered world action, "
            "or 'respond' to end the turn and return results to the host."
        ),
    )
    action_type: Optional[str] = Field(
        default=None,
        description="Registered action type when kind is 'action'.",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the action, matching the action schema.",
    )
    target_id: Optional[str] = Field(
        default=None,
        description="Optional primary target entity ID.",
    )
    reason: Optional[str] = Field(
        default=None,
        description="Brief reason for this decision.",
    )


class DialogueLineDraft(BaseModel):
    character_id: str = Field(..., description="ID of the speaking character.")
    character_name: str = Field(..., description="Display name of the speaker.")
    text: str = Field(..., description="Exact words spoken.")
    emotion: Optional[str] = Field(
        default=None,
        description="Optional emotion for this line.",
    )


class GeneratedPresentation(BaseModel):
    """Structured LLM output for host-facing presentation after a step."""

    narrative: str = Field(
        ...,
        description="Short third-person narration of what just happened.",
    )
    lines: list[DialogueLineDraft] = Field(
        default_factory=list,
        description="Spoken lines when speaking events occurred; otherwise empty.",
    )


# Backward-compatible alias.
GeneratedDialogue = GeneratedPresentation


class InteractionState(TypedDict, total=False):
    """LangGraph state for one player message (act-one loop)."""

    message: str
    actor_id: str
    interaction_id: str
    session_id: str
    context: dict[str, Any]
    decision: dict[str, Any]
    last_rejection: Optional[str]
    last_events: list[dict[str, Any]]
    speaking_pending: bool
    presentation_pending: bool
    step_count: int
    max_steps: int
    done: bool
    status: str
    events: Annotated[list[dict[str, Any]], operator.add]
    dialogue: Annotated[list[dict[str, Any]], operator.add]
    narrative_parts: Annotated[list[str], operator.add]
    actions: Annotated[list[dict[str, Any]], operator.add]
    trace_steps: Annotated[list[str], operator.add]
