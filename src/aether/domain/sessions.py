from __future__ import annotations

import warnings
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from aether.domain.interactions import (
    Interaction,
    InteractionHistory,
    InteractionResult,
    InteractionStatus,
)
from aether.components.shared import new_id
from aether.components.timeline import Branch, Timeline


class RuntimeContext(BaseModel):
    """
    Lightweight session context used by runtime systems.
    """

    recent_event_ids: List[str] = Field(
        default_factory=list,
        description="IDs of recent events relevant to the current runtime context.",
    )

    active_character_ids: List[str] = Field(
        default_factory=list,
        description="Character IDs currently active in the session context.",
    )


class Session(BaseModel):
    """
    Session of a world.
    """

    id: str = Field(
        default_factory=lambda: new_id("session"),
        description="Unique identifier for this session.",
    )

    world_id: str = Field(
        ...,
        description="ID of the world this session belongs to.",
    )

    external_player_id: Optional[str] = Field(
        default=None,
        description="Optional external user/player identifier from the host application.",
    )

    timeline: Timeline = Field(
        default_factory=Timeline,
        description="Timeline state containing branches and turns.",
    )

    history: InteractionHistory = Field(
        default_factory=InteractionHistory,
        description="Ordered interaction history for this session.",
    )

    context: RuntimeContext = Field(
        default_factory=RuntimeContext,
        description="Runtime context used during interaction processing.",
    )

    current_branch_id: str = Field(
        default="main",
        description="ID of the currently active branch.",
    )

    def model_post_init(self, __context: Any) -> None:
        self.timeline.ensure_main_branch()

    def interact(
        self,
        message: str,
        actor_id: str = "player",
        idempotency_key: Optional[str] = None,
    ) -> InteractionResult:
        """
        Deprecated placeholder.

        Use ``Aether.interact(world, session, message, actor_id=...)`` instead.
        This method only records an empty completed interaction for compatibility.
        """
        warnings.warn(
            "Session.interact is deprecated; use Aether.interact instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        interaction = Interaction.from_message(
            session_id=self.id,
            branch_id=self.current_branch_id,
            message=message,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )

        self.history.add(interaction)

        turn = self.timeline.next_turn(
            branch_id=self.current_branch_id,
            interaction_id=interaction.id,
        )

        interaction.trace.add_step(f"Created turn {turn.number}")
        interaction.trace.add_step(
            "Deprecated Session.interact; use Aether.interact"
        )

        result = InteractionResult(
            interaction_id=interaction.id,
            status=InteractionStatus.COMPLETED,
            dialogue=[],
            narrative=None,
            events=[],
        )

        interaction.result = result
        interaction.status = InteractionStatus.COMPLETED

        return result

    def branch(self, from_turn_id: Optional[str] = None) -> Branch:
        branch = self.timeline.fork(
            from_turn_id=from_turn_id,
            parent_branch_id=self.current_branch_id,
        )

        self.current_branch_id = branch.id
        return branch