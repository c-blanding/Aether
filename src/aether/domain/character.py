from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from aether.components.shared import new_id

from aether.components.capatability import CapabilitySet
from aether.components.goal import GoalManager, Goal
from aether.components.inventory import Inventory
from aether.cognition.knowledge import Knowledge, Belief
from aether.cognition.memory import Memory, MemoryRecord, PinnedFact, PinnedKind, RecallPack
from aether.components.planner import Planner
from aether.domain.relationship import RelationshipManager, Relationship


class CharacterIdentity(BaseModel):
    """
    Stable identity information for a character.
    """

    name: str = Field(
        ...,
        description="Display name of the character.",
        examples=["Arthur"],
    )

    role: str = Field(
        default="",
        description="Narrative or gameplay role for the character.",
        examples=["Butler"],
    )

    background: str = Field(
        default="",
        description="Backstory or contextual description for the character.",
    )


class CharacterState(BaseModel):
    """
    Mutable runtime state for a character.
    """

    emotion: str = Field(
        default="neutral",
        description="Current emotional state of the character.",
        examples=["neutral", "fear", "anger"],
    )

    status: str = Field(
        default="active",
        description="Current gameplay status of the character.",
        examples=["active", "inactive", "frozen"],
    )

    location_id: Optional[str] = Field(
        default=None,
        description="ID of the location where the character currently is.",
    )


class Personality(BaseModel):
    """
    Personality data that guides AI behavior and dialogue generation.
    """

    traits: List[str] = Field(
        default_factory=list,
        description="Personality traits for the character.",
        examples=[["loyal", "secretive", "formal"]],
    )

    values: List[str] = Field(
        default_factory=list,
        description="Values or principles that influence the character.",
    )

    fears: List[str] = Field(
        default_factory=list,
        description="Fears or anxieties that influence character behavior.",
    )

    speaking_style: Optional[str] = Field(
        default=None,
        description="Optional natural-language description of the character's speaking style.",
        examples=["Formal, reserved, and indirect."],
    )






class Character(BaseModel):
    """
    Intelligent character inside a the World.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str = Field(
        default_factory=lambda: new_id("char"),
        description="Unique identifier for this character.",
    )

    identity: CharacterIdentity = Field(
        ...,
        description="Stable identity information for the character.",
    )

    state: CharacterState = Field(
        default_factory=CharacterState,
        description="Mutable runtime state such as emotion, status, and location.",
    )

    personality: Personality = Field(
        default_factory=Personality,
        description="Character personality traits, values, fears, and speaking style.",
    )

    memory: Memory = Field(
        default_factory=Memory,
        description="Character memory system containing episodic, semantic, and working memory.",
    )

    knowledge: Knowledge = Field(
        default_factory=Knowledge,
        description="Character knowledge and beliefs.",
    )

    goals: GoalManager = Field(
        default_factory=GoalManager,
        description="Character goals grouped by active, completed, and failed status.",
    )

    relationships: RelationshipManager = Field(
        default_factory=RelationshipManager,
        description="Directional relationships from this character to other characters.",
    )

    inventory: Inventory = Field(
        default_factory=Inventory,
        description="Items currently held by this character.",
    )

    capabilities: CapabilitySet = Field(
        default_factory=CapabilitySet,
        description="Actions or mechanics this character is capable of performing.",
    )

    planner: Planner = Field(
        default_factory=Planner,
        description="Placeholder planning strategy for future AI behavior.",
    )

    @property
    def name(self) -> str:
        return self.identity.name

    @property
    def role(self) -> str:
        return self.identity.role

    def add_goal(self, description: str, priority: int = 50) -> Goal:
        return self.goals.add(description, priority)

    def remember(
        self,
        summary: str,
        perspective: str | None = None,
        importance: float = 0.5,
        emotional_weight: float = 0.0,
        emotion: Optional[str] = None,
        source_event_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        participant_ids: Optional[List[str]] = None,
        location_ids: Optional[List[str]] = None,
    ) -> MemoryRecord:
        return self.memory.remember(
            summary=summary,
            perspective=perspective or summary,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            source_event_ids=source_event_ids,
            tags=tags,
            participant_ids=participant_ids,
            location_ids=location_ids,
        )

    def recall(
        self,
        query: str,
        *,
        location_ids: Optional[List[str]] = None,
        participant_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
        min_importance: float = 0.0,
    ) -> List[MemoryRecord]:
        return self.memory.search(
            query,
            limit=limit,
            location_ids=location_ids,
            participant_ids=participant_ids,
            tags=tags,
            min_importance=min_importance,
        )

    def pin_fact(
        self,
        text: str,
        *,
        key: str = "",
        kind: PinnedKind = "host",
    ) -> PinnedFact:
        """Pin a fact card that later prompts keep without the full episodic log."""
        return self.memory.pin(text, key=key, kind=kind)

    def recall_pack(
        self,
        query: str,
        *,
        goals: Optional[List[str]] = None,
        relationship_ids: Optional[List[str]] = None,
        location_ids: Optional[List[str]] = None,
        participant_ids: Optional[List[str]] = None,
        extra_pinned: Optional[List[str]] = None,
        limit: int = 4,
    ) -> RecallPack:
        if goals is None:
            goals = [goal.description for goal in self.goals.prioritize()[:4]]
        if relationship_ids is None:
            relationship_ids = [
                rel.target_character_id
                for rel in self.relationships.relationships.values()
                if abs(rel.trust) + abs(rel.affinity) + abs(rel.fear) + abs(rel.suspicion)
                >= 0.05
            ]
        return self.memory.pack_recall(
            query,
            goals=goals,
            relationship_ids=relationship_ids,
            location_ids=location_ids,
            participant_ids=participant_ids,
            extra_pinned=extra_pinned,
            limit=limit,
        )

    def learn(
        self,
        proposition: str,
        believed_value: str = "true",
        confidence: float = 1.0,
        source_event_ids: Optional[List[str]] = None,
    ) -> Belief:
        return self.knowledge.learn(
            proposition=proposition,
            believed_value=believed_value,
            confidence=confidence,
            source_event_ids=source_event_ids,
        )

    def knows(self, belief_id: str) -> bool:
        return self.knowledge.knows(belief_id)

    def forget_belief(self, belief_id: str) -> None:
        self.knowledge.forget(belief_id)

    def add_capability(self, capability: str) -> None:
        self.capabilities.add(capability)

    def can(self, capability: str) -> bool:
        return self.capabilities.allows(capability)

    def add_item(self, item_id: str) -> None:
        self.inventory.add(item_id)

    def remove_item(self, item_id: str) -> None:
        self.inventory.remove(item_id)

    def has_item(self, item_id: str) -> bool:
        return self.inventory.contains(item_id)

    def update_relationship(
        self,
        target_character_id: str,
        trust_delta: float = 0.0,
        affinity_delta: float = 0.0,
        fear_delta: float = 0.0,
        suspicion_delta: float = 0.0,
    ) -> Relationship:
        return self.relationships.update(
            target_character_id=target_character_id,
            trust_delta=trust_delta,
            affinity_delta=affinity_delta,
            fear_delta=fear_delta,
            suspicion_delta=suspicion_delta,
        )