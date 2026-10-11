from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from aether.components.shared import utc_now, new_id


class Message(BaseModel):
    role: str
    content: str
    name: str = None

class WorkingMemoryItem(BaseModel):
    """
    Temporary memory item currently active in a character's mind.
    """

    id: str = Field(
        default_factory=lambda: new_id("wm"),
        description="Unique identifier for this working memory item.",
    )

    text: str = Field(
        ...,
        description="Short text currently active in the character's working memory.",
    )

    source_event_ids: List[str] = Field(
        default_factory=list,
        description="World event IDs that caused this working memory item.",
    )

    importance: float = Field(
        default=0.5,
        description="Importance score for this working memory item.",
        ge=0.0,
        le=1.0,
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this working memory item was created.",
    )

class MemoryRecord(BaseModel):
    """
    A subjective episodic memory owned by a character.

    The same event can create different memories for different characters.
    """

    id: str = Field(
        default_factory=lambda: new_id("mem"),
        description="Unique identifier for this memory.",
    )

    summary: str = Field(
        ...,
        description="Subjective natural-language summary of what the character remembers.",
    )

    perspective: str = Field(
        ...,
        description="Character-specific interpretation of the event.",
        examples=["I saw the Detective pick up the Old Key."],
    )

    source_event_ids: List[str] = Field(
        default_factory=list,
        description="World event IDs that caused or support this memory.",
    )

    importance: float = Field(
        default=0.5,
        description="Importance score for retrieval and consolidation.",
        ge=0.0,
        le=1.0,
    )

    emotional_weight: float = Field(
        default=0.0,
        description="Emotional intensity attached to this memory.",
        ge=0.0,
        le=1.0,
    )

    emotion: Optional[str] = Field(
        default=None,
        description="Primary emotion associated with this memory.",
        examples=["fear", "anger", "curiosity"],
    )

    confidence: float = Field(
        default=1.0,
        description="How confident the character is in this memory.",
        ge=0.0,
        le=1.0,
    )

    tags: List[str] = Field(
        default_factory=list,
        description="Tags used for retrieval and filtering.",
    )

    participant_ids: List[str] = Field(
        default_factory=list,
        description="Character IDs involved in the remembered event.",
    )

    location_ids: List[str] = Field(
        default_factory=list,
        description="Location IDs related to the memory.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this memory was created.",
    )


class MemorySummary(BaseModel):
    """
    Consolidated semantic memory created from multiple episodic memories.
    """

    id: str = Field(
        default_factory=lambda: new_id("msum"),
        description="Unique identifier for this memory summary.",
    )

    statement: str = Field(
        ...,
        description="Higher-level learned statement derived from memories.",
    )

    source_memory_ids: List[str] = Field(
        default_factory=list,
        description="Memory IDs that contributed to this summary.",
    )

    confidence: float = Field(
        default=0.8,
        description="Confidence score for the summary.",
        ge=0.0,
        le=1.0,
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this memory summary was created.",
    )


class Memory(BaseModel):
    """
    Character memory system.

    Working memory is temporary.
    Episodic memory stores subjective experiences.
    Semantic memory stores consolidated learned statements.
    """

    working: List[WorkingMemoryItem] = Field(
        default_factory=list,
        description="Temporary memories currently active in the character's mind.",
    )

    episodic: List[MemoryRecord] = Field(
        default_factory=list,
        description="Specific subjective memories from experienced or witnessed events.",
    )

    semantic: List[MemorySummary] = Field(
        default_factory=list,
        description="Consolidated higher-level memories derived from episodes.",
    )

    def add_working(
        self,
        text: str,
        importance: float = 0.5,
        source_event_ids: Optional[List[str]] = None,
    ) -> WorkingMemoryItem:
        item = WorkingMemoryItem(
            text=text,
            importance=importance,
            source_event_ids=source_event_ids or [],
        )

        self.working.append(item)
        return item

    def remember(
        self,
        summary: str,
        perspective: str,
        importance: float = 0.5,
        emotional_weight: float = 0.0,
        emotion: Optional[str] = None,
        confidence: float = 1.0,
        source_event_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        participant_ids: Optional[List[str]] = None,
        location_ids: Optional[List[str]] = None,
    ) -> MemoryRecord:
        memory = MemoryRecord(
            summary=summary,
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            confidence=confidence,
            source_event_ids=source_event_ids or [],
            tags=tags or [],
            participant_ids=participant_ids or [],
            location_ids=location_ids or [],
        )

        self.episodic.append(memory)
        return memory

    def search(
        self,
        query: str,
        limit: int = 10,
        *,
        location_ids: Optional[List[str]] = None,
        participant_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        min_importance: float = 0.0,
    ) -> List[MemoryRecord]:
        """
        Lexical recall with optional filters.

        When filters are provided, matching memories get a score boost and
        non-matching memories are soft-penalized (not hard-excluded) so sparse
        memories still surface if nothing else matches.
        """
        normalized_query = (query or "").lower().strip()
        query_tokens = [token for token in normalized_query.split() if token]
        location_filter = set(location_ids or [])
        participant_filter = set(participant_ids or [])
        tag_filter = {tag.lower() for tag in (tags or [])}

        scored: List[tuple[float, MemoryRecord]] = []

        for memory in self.episodic:
            if memory.importance < min_importance:
                continue

            text = (
                f"{memory.summary} {memory.perspective} {' '.join(memory.tags)}"
            ).lower()

            if normalized_query and normalized_query in text:
                relevance = 1.0
            elif query_tokens:
                hits = sum(1 for token in query_tokens if token in text)
                relevance = hits / len(query_tokens)
            else:
                relevance = 0.35  # empty query → recency/importance ranking

            score = (
                relevance * 0.40
                + memory.importance * 0.30
                + memory.emotional_weight * 0.20
            )

            if location_filter:
                if location_filter & set(memory.location_ids):
                    score += 0.15
                else:
                    score -= 0.05

            if participant_filter:
                if participant_filter & set(memory.participant_ids):
                    score += 0.15
                else:
                    score -= 0.05

            if tag_filter:
                memory_tags = {tag.lower() for tag in memory.tags}
                if tag_filter & memory_tags:
                    score += 0.1
                else:
                    score -= 0.03

            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [memory for _, memory in scored[:limit]]

    def consolidate(self, limit: int = 5) -> Optional[MemorySummary]:
        if not self.episodic:
            return None

        recent = self.episodic[-limit:]

        summary = MemorySummary(
            statement="; ".join(memory.summary for memory in recent),
            source_memory_ids=[memory.id for memory in recent],
        )

        self.semantic.append(summary)
        return summary