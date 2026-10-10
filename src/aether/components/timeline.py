from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from aether.components.shared import new_id, utc_now


class Branch(BaseModel):
    """
    A timeline branch inside a session.
    """

    id: str = Field(
        default_factory=lambda: new_id("branch"),
        description="Unique identifier for this branch.",
    )

    parent_branch_id: Optional[str] = Field(
        default=None,
        description="ID of the parent branch this branch forked from.",
    )

    fork_turn_id: Optional[str] = Field(
        default=None,
        description="ID of the turn where this branch was created.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this branch was created.",
    )


class Turn(BaseModel):
    """
    A single ordered turn inside a branch.
    """

    id: str = Field(
        default_factory=lambda: new_id("turn"),
        description="Unique identifier for this turn.",
    )

    branch_id: str = Field(
        ...,
        description="ID of the branch this turn belongs to.",
    )

    number: int = Field(
        ...,
        description="Turn number within the branch.",
        ge=1,
    )

    interaction_id: Optional[str] = Field(
        default=None,
        description="ID of the interaction associated with this turn.",
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        description="UTC timestamp when this turn was created.",
    )


class Timeline(BaseModel):
    """
    Timeline state for a session, including branches and turns.
    """

    branches: Dict[str, Branch] = Field(
        default_factory=dict,
        description="Mapping of branch ID to Branch.",
    )

    turns: List[Turn] = Field(
        default_factory=list,
        description="Ordered turns across all branches.",
    )

    def ensure_main_branch(self) -> Branch:
        if "main" not in self.branches:
            self.branches["main"] = Branch(
                id="main",
                parent_branch_id=None,
                fork_turn_id=None,
            )

        return self.branches["main"]

    def fork(
        self,
        from_turn_id: Optional[str] = None,
        parent_branch_id: str = "main",
    ) -> Branch:
        branch = Branch(
            parent_branch_id=parent_branch_id,
            fork_turn_id=from_turn_id,
        )

        self.branches[branch.id] = branch
        return branch

    def next_turn(
        self,
        branch_id: str,
        interaction_id: Optional[str] = None,
    ) -> Turn:
        branch_turns = [
            turn
            for turn in self.turns
            if turn.branch_id == branch_id
        ]

        turn = Turn(
            branch_id=branch_id,
            number=len(branch_turns) + 1,
            interaction_id=interaction_id,
        )

        self.turns.append(turn)
        return turn