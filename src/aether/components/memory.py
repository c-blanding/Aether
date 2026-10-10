from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from aether.components.shared import utc_now, new_id


class Message(BaseModel):
    role: str
    content: str
    name: str = None

class MemoryRecord(BaseModel):
    """
    A single episodic memory remembered by a character.
    """

    id: str = Field(
        default_factory=lambda: new_id("mem"),
        description="Unique identifier for this memory.",
    )

    summary: str = Field(
        ...,
        description="Natural-language summary of the remembered event or experience.",
    )

    importance: float = Field(
        default=0.5,
        description="Importance score for retrieval and consolidation.",
        ge=0.0,
        le=1.0,
    )

    emotion: Optional[str] = Field(
        default=None,
        description="Emotion associated with this memory.",
    )

    source_event_ids: List[str] = Field(
        default_factory=list,
        description="World event IDs that caused or support this memory.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this memory was created.",
    )


class MemorySummary(BaseModel):
    """
    A consolidated semantic memory summary.
    """

    id: str = Field(
        default_factory=lambda: new_id("msum"),
        description="Unique identifier for this memory summary.",
    )

    summary: str = Field(
        ...,
        description="Natural-language summary of multiple related memories.",
    )

    source_memory_ids: List[str] = Field(
        default_factory=list,
        description="Memory IDs that contributed to this summary.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this memory summary was created.",
    )


class Memory(BaseModel):
    """
    Character memory system.

    Memory is experiential. Knowledge is propositional.
    """

    episodic: List[MemoryRecord] = Field(
        default_factory=list,
        description="Specific remembered experiences.",
    )

    semantic: List[MemorySummary] = Field(
        default_factory=list,
        description="Summarized or consolidated knowledge derived from memories.",
    )

    working: List[str] = Field(
        default_factory=list,
        description="Temporary working-memory notes used during active reasoning.",
    )

    def remember(
        self,
        summary: str,
        importance: float = 0.5,
        emotion: Optional[str] = None,
        source_event_ids: Optional[List[str]] = None,
    ) -> MemoryRecord:
        memory = MemoryRecord(
            summary=summary,
            importance=importance,
            emotion=emotion,
            source_event_ids=source_event_ids or [],
        )

        self.episodic.append(memory)
        return memory

    def search(self, query: str) -> List[MemoryRecord]:
        normalized_query = query.lower()

        return [
            memory
            for memory in self.episodic
            if normalized_query in memory.summary.lower()
        ]

    def consolidate(self, limit: int = 5) -> Optional[MemorySummary]:
        if not self.episodic:
            return None

        recent = self.episodic[-limit:]

        summary = MemorySummary(
            summary="; ".join(memory.summary for memory in recent),
            source_memory_ids=[memory.id for memory in recent],
        )

        self.semantic.append(summary)
        return summary