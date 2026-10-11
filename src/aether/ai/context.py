from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from aether.domain.character import Personality
from aether.domain.presentation import PresentationStyle, SceneSummary


class LocationBrief(BaseModel):
    """Location summary for prompts."""

    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None


class ConnectedLocationBrief(BaseModel):
    id: str
    name: str


class NearbyCharacterBrief(BaseModel):
    """Lightweight nearby character for scene staging."""

    id: str
    name: str
    role: str = ""
    emotion: str = "neutral"


class VisibleItemBrief(BaseModel):
    id: str
    name: str
    description: str = ""
    owner_id: Optional[str] = None
    location_id: Optional[str] = None


class RelationshipBrief(BaseModel):
    """Directional relationship snapshot for prompts."""

    target_character_id: str
    trust: float = 0.0
    affinity: float = 0.0
    fear: float = 0.0
    suspicion: float = 0.0


class ScenePayload(BaseModel):
    """Scene packet passed to narrative/dialogue renderers."""

    world_name: Optional[str] = None
    world_description: Optional[str] = None
    location: LocationBrief = Field(default_factory=LocationBrief)
    nearby_characters: list[NearbyCharacterBrief] = Field(default_factory=list)
    visible_items: list[VisibleItemBrief] = Field(default_factory=list)
    event_types: list[Optional[str]] = Field(default_factory=list)
    scene_summary: SceneSummary = Field(default_factory=SceneSummary)


class GoalBrief(BaseModel):
    description: str
    priority: int = 50


class BeliefBrief(BaseModel):
    proposition: str
    believed_value: str = "true"
    confidence: float = 1.0


class MemoryBrief(BaseModel):
    perspective: str
    importance: float = 0.5
    emotion: Optional[str] = None
    source: str = Field(
        default="episodic",
        description="episodic, pinned, or semantic.",
    )


class CharacterBrief(BaseModel):
    """Character packet for narrative/dialogue renderers."""

    id: str
    name: str
    role: str = ""
    background: str = ""
    personality: Personality = Field(default_factory=Personality)
    emotion: str = "neutral"
    status: str = "active"
    location: LocationBrief = Field(default_factory=LocationBrief)
    goals: list[GoalBrief] = Field(default_factory=list)
    beliefs: list[BeliefBrief] = Field(default_factory=list)
    memories: list[MemoryBrief] = Field(default_factory=list)
    pinned_facts: list[str] = Field(default_factory=list)
    semantic_memories: list[str] = Field(default_factory=list)
    relationships: list[RelationshipBrief] = Field(default_factory=list)


class PresentationTone(BaseModel):
    """Hints for presentation renderers (not genre locks)."""

    generation_mode: str = "narrative_then_dialogue"
    has_speaking_events: bool = False
    style: PresentationStyle = Field(default_factory=PresentationStyle)


class ActorContext(BaseModel):
    """Acting character snapshot for the decide planner."""

    id: str
    name: str
    location_id: Optional[str] = None
    location_name: Optional[str] = None
    inventory: list[str] = Field(default_factory=list)


class PlannerLocationContext(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    connected_locations: list[ConnectedLocationBrief] = Field(default_factory=list)


class PlannerCharacterContext(BaseModel):
    """Richer nearby character view for action planning."""

    id: str
    name: str
    role: str = ""
    emotion: str = "neutral"
    goals: list[GoalBrief] = Field(default_factory=list)
    beliefs: list[str] = Field(default_factory=list)
    memories: list[str] = Field(default_factory=list)
    personality: Personality = Field(default_factory=Personality)
    relationship_to_actor: Optional[RelationshipBrief] = None


class ActionSchemaBrief(BaseModel):
    type: str
    module: str
    required_capability: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)


class ActOneContext(BaseModel):
    """World context gathered for the act-one decide node."""

    actor: ActorContext
    location: PlannerLocationContext = Field(default_factory=PlannerLocationContext)
    nearby_characters: list[PlannerCharacterContext] = Field(default_factory=list)
    nearby_items: list[VisibleItemBrief] = Field(default_factory=list)
    available_actions: list[ActionSchemaBrief] = Field(default_factory=list)
    recent_event_types: list[str] = Field(default_factory=list)
    scene_summary: SceneSummary = Field(default_factory=SceneSummary)
