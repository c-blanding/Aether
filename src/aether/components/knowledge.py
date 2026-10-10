from datetime import datetime
from typing import List, Optional, Dict

from pydantic import BaseModel, Field

from aether.components.shared import new_id, utc_now


class Belief(BaseModel):
    """
    A proposition believed by a character.

    Beliefs can be false.
    """

    id: str = Field(
        default_factory=lambda: new_id("belief"),
        description="Unique identifier for this belief.",
    )

    proposition: str = Field(
        ...,
        description="The proposition the character believes.",
        examples=["No one saw Arthur enter the study."],
    )

    believed_value: str = Field(
        default="true",
        description="The value the character believes for the proposition.",
        examples=["true", "false", "unknown"],
    )

    confidence: float = Field(
        default=1.0,
        description="Confidence score for this belief.",
        ge=0.0,
        le=1.0,
    )

    source_event_ids: List[str] = Field(
        default_factory=list,
        description="World event IDs that caused or support this belief.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this belief was created.",
    )


class Knowledge(BaseModel):
    """
    Character knowledge and belief system.
    """

    beliefs: Dict[str, Belief] = Field(
        default_factory=dict,
        description="Mapping of belief ID to Belief objects.",
    )

    def learn(
        self,
        proposition: str,
        believed_value: str = "true",
        confidence: float = 1.0,
        source_event_ids: Optional[List[str]] = None,
    ) -> Belief:
        belief = Belief(
            proposition=proposition,
            believed_value=believed_value,
            confidence=confidence,
            source_event_ids=source_event_ids or [],
        )

        self.beliefs[belief.id] = belief
        return belief

    def knows(self, belief_id: str) -> bool:
        return belief_id in self.beliefs

    def get(self, belief_id: str) -> Optional[Belief]:
        return self.beliefs.get(belief_id)

    def forget(self, belief_id: str) -> None:
        self.beliefs.pop(belief_id, None)