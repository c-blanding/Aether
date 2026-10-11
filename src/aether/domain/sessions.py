from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aether.components.shared import AetherValidationError, new_id
from aether.components.timeline import Branch, Timeline, Turn
from aether.domain.interactions import (
    Interaction,
    InteractionHistory,
    InteractionResult,
    InteractionStatus,
)
from aether.domain.presentation import SceneSummary
from aether.domain.snapshot import WorldSnapshot

if TYPE_CHECKING:
    from aether.domain.world import World


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

    scene_summary: SceneSummary = Field(
        default_factory=SceneSummary,
        description=(
            "Rolling scene continuity summary injected into gather/decide/"
            "presentation prompts."
        ),
    )

    current_branch_id: str = Field(
        default="main",
        description="ID of the currently active branch.",
    )

    branch_snapshots: Dict[str, WorldSnapshot] = Field(
        default_factory=dict,
        description="Latest world snapshot for each branch tip.",
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

    def sync_tip(self, world: World) -> WorldSnapshot:
        """Persist the live world as the current branch tip snapshot."""
        if world.id != self.world_id:
            raise AetherValidationError(
                "Cannot sync session tip from a different world."
            )
        snapshot = WorldSnapshot.capture(world)
        self.branch_snapshots[self.current_branch_id] = snapshot
        return snapshot

    def remember_turn(self, world: World, turn: Turn) -> WorldSnapshot:
        """Capture world state onto a completed turn and the branch tip."""
        snapshot = self.sync_tip(world)
        # Tip and turn share this object until the next sync_tip replaces the tip.
        turn.snapshot = snapshot
        return snapshot

    def branch(
        self,
        world: World,
        from_turn_id: Optional[str] = None,
    ) -> Branch:
        """
        Fork the timeline into an isolated branch and apply its world state.

        Without ``from_turn_id``, forks from the latest turn on the current
        branch (or the current tip if there are no turns yet). With
        ``from_turn_id``, restores that turn's snapshot (must be on the
        current branch and must have been captured).
        """
        if world.id != self.world_id:
            raise AetherValidationError(
                "Cannot branch a session against a different world."
            )

        self.sync_tip(world)

        parent_branch_id = self.current_branch_id
        parent_turns = self.timeline.turns_for_branch(parent_branch_id)

        if from_turn_id is None:
            from_turn_id = parent_turns[-1].id if parent_turns else None

        if from_turn_id is not None:
            turn = self.timeline.get_turn(from_turn_id)
            if turn is None:
                raise AetherValidationError(f"Unknown turn: {from_turn_id}")
            if turn.branch_id != parent_branch_id:
                raise AetherValidationError(
                    "from_turn_id must belong to the current branch; "
                    "checkout that branch first."
                )
            if turn.snapshot is None:
                raise AetherValidationError(
                    f"Turn {from_turn_id} has no world snapshot; "
                    "cannot fork from it."
                )
            snapshot = turn.snapshot.clone()
        else:
            tip = self.branch_snapshots[parent_branch_id]
            snapshot = tip.clone()

        branch = self.timeline.fork(
            from_turn_id=from_turn_id,
            parent_branch_id=parent_branch_id,
        )
        self.branch_snapshots[branch.id] = snapshot
        self.current_branch_id = branch.id
        snapshot.apply_to(world)
        return branch

    def checkout(self, world: World, branch_id: str) -> Branch:
        """
        Switch the active branch, saving the current tip and restoring the target.
        """
        if world.id != self.world_id:
            raise AetherValidationError(
                "Cannot checkout a session against a different world."
            )
        if branch_id not in self.timeline.branches:
            raise AetherValidationError(f"Unknown branch: {branch_id}")

        if branch_id == self.current_branch_id:
            self.sync_tip(world)
            return self.timeline.branches[branch_id]

        self.sync_tip(world)
        tip = self.branch_snapshots.get(branch_id)
        if tip is None:
            raise AetherValidationError(
                f"Branch '{branch_id}' has no world snapshot."
            )

        self.current_branch_id = branch_id
        tip.apply_to(world)
        return self.timeline.branches[branch_id]

    def visible_interaction_ids(self, branch_id: Optional[str] = None) -> set[str]:
        """
        Interaction IDs visible on a branch, including inherited ancestor turns
        up to each fork point.
        """
        target = branch_id or self.current_branch_id
        if target not in self.timeline.branches:
            return set()

        chain: List[Branch] = []
        cursor: Optional[str] = target
        while cursor is not None:
            branch = self.timeline.branches[cursor]
            chain.append(branch)
            cursor = branch.parent_branch_id

        visible: set[str] = set()
        for index, branch in enumerate(chain):
            if index == 0:
                max_number: Optional[int] = None
            else:
                child = chain[index - 1]
                if child.fork_turn_id is None:
                    max_number = None
                else:
                    fork_turn = self.timeline.get_turn(child.fork_turn_id)
                    if fork_turn is None:
                        raise AetherValidationError(
                            f"Fork turn '{child.fork_turn_id}' is missing "
                            f"for branch '{child.id}'."
                        )
                    max_number = fork_turn.number

            for turn in self.timeline.turns_for_branch(branch.id):
                if max_number is not None and turn.number > max_number:
                    continue
                if turn.interaction_id is not None:
                    visible.add(turn.interaction_id)

        return visible

    def history_for_branch(
        self,
        branch_id: Optional[str] = None,
    ) -> List[Interaction]:
        """Lineage-aware interaction history for a branch."""
        return self.history.by_ids(self.visible_interaction_ids(branch_id))
