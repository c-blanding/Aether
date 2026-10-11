from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class Relationship(BaseModel):
    """
    Directional relationship from one character to another.
    """

    target_character_id: str = Field(
        ...,
        description="ID of the character this relationship points to.",
    )

    trust: float = Field(
        default=0.0,
        description="Trust score toward the target character.",
    )

    affinity: float = Field(
        default=0.0,
        description="Affinity or liking score toward the target character.",
    )

    fear: float = Field(
        default=0.0,
        description="Fear score toward the target character.",
    )

    suspicion: float = Field(
        default=0.0,
        description="Suspicion score toward the target character.",
    )


class RelationshipDelta(BaseModel):
    """One directional relationship change applied during a turn."""

    from_character_id: str = Field(
        ...,
        description="Character whose relationship scores were updated.",
    )
    to_character_id: str = Field(
        ...,
        description="Target of the updated relationship.",
    )
    trust_delta: float = Field(default=0.0)
    affinity_delta: float = Field(default=0.0)
    fear_delta: float = Field(default=0.0)
    suspicion_delta: float = Field(default=0.0)
    reason: str = Field(
        default="",
        description="Short reason for the delta (event type / social cue).",
    )
    event_id: Optional[str] = Field(
        default=None,
        description="Source event ID when available.",
    )


class RelationshipManager(BaseModel):
    """
    Manages directional relationships from this character to other characters.
    """

    relationships: Dict[str, Relationship] = Field(
        default_factory=dict,
        description="Mapping of target character ID to relationship state.",
    )

    def get(self, target_character_id: str) -> Relationship:
        if target_character_id not in self.relationships:
            self.relationships[target_character_id] = Relationship(
                target_character_id=target_character_id
            )

        return self.relationships[target_character_id]

    def update(
        self,
        target_character_id: str,
        trust_delta: float = 0.0,
        affinity_delta: float = 0.0,
        fear_delta: float = 0.0,
        suspicion_delta: float = 0.0,
    ) -> Relationship:
        relationship = self.get(target_character_id)

        relationship.trust += trust_delta
        relationship.affinity += affinity_delta
        relationship.fear += fear_delta
        relationship.suspicion += suspicion_delta

        return relationship