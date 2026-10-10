from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aether.components.shared import new_id, utc_now


class WorldActionEvent(BaseModel):
    """
    Modular event data.

    Represents the confirmed outcome produced by an action handler.
    """

    type: str = Field(
        ...,
        description="The confirmed event type, such as 'item_picked_up', 'dialogue_spoken', or 'evidence_presented'.",
        examples=["item_picked_up"],
    )

    module: Optional[str] = Field(
        default=None,
        description="The module that produced this event.",
        examples=["inventory"],
    )

    version: int = Field(
        default=1,
        description="Version number for the event schema.",
        ge=1,
    )

    attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event-specific attributes validated by the module's registered event schema.",
        examples=[
            {
                "item_id": "item_old_key",
                "previous_location_id": "loc_library",
                "new_owner_id": "char_player",
            }
        ],
    )


class WorldEvent(BaseModel):
    """
    Confirmed historical record.

    Events are durable facts in the simulation.
    Actions are only attempts.
    """

    id: str = Field(
        default_factory=lambda: new_id("evt"),
        description="Unique identifier for this committed world event.",
        examples=["evt_abc123"],
    )

    world_id: Optional[str] = Field(
        default=None,
        description="ID of the world where this event occurred.",
    )

    session_id: Optional[str] = Field(
        default=None,
        description="ID of the session where this event occurred.",
    )

    branch_id: Optional[str] = Field(
        default=None,
        description="ID of the timeline branch where this event occurred.",
        examples=["main"],
    )

    interaction_id: Optional[str] = Field(
        default=None,
        description="ID of the interaction that produced this event.",
    )

    actor_id: Optional[str] = Field(
        default=None,
        description="ID of the actor responsible for this event.",
    )

    target_ids: List[str] = Field(
        default_factory=list,
        description="IDs of entities affected by this event.",
    )

    data: WorldActionEvent = Field(
        ...,
        description="Modular event payload containing the event type, module, version, and attributes.",
    )

    witnessed_by: List[str] = Field(
        default_factory=list,
        description="Character IDs that witnessed this event.",
    )

    occurred_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when the event occurred.",
    )

    schema_version: int = Field(
        default=1,
        description="Version of the WorldEvent envelope schema.",
        ge=1,
    )

    @property
    def type(self) -> str:
        return self.data.type

    @property
    def module(self) -> Optional[str]:
        return self.data.module


class EventStore(BaseModel):
    """
    Append-only in-memory event store for a world.

    In production, this maps to an events database table.
    """

    events: List[WorldEvent] = Field(
        default_factory=list,
        description="Committed world events in chronological order.",
    )

    def append(self, event: WorldEvent) -> None:
        self.events.append(event)

    def append_many(self, events: List[WorldEvent]) -> None:
        self.events.extend(events)

    def latest(self, limit: int = 10) -> List[WorldEvent]:
        return self.events[-limit:]

    def by_type(self, event_type: str) -> List[WorldEvent]:
        return [
            event
            for event in self.events
            if event.type == event_type
        ]

    def by_actor(self, actor_id: str) -> List[WorldEvent]:
        return [
            event
            for event in self.events
            if event.actor_id == actor_id
        ]

    def by_witness(self, character_id: str) -> List[WorldEvent]:
        return [
            event
            for event in self.events
            if character_id in event.witnessed_by
        ]