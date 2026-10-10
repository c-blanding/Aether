from typing import List
from uuid import uuid4, UUID

from pydantic import BaseModel, Field

from aether.components.shared import AetherValidationError, new_id


class Goal(BaseModel):
    """
    A goal owned by a character.
    """

    id: str = Field(
        default_factory=lambda: new_id("goal"),
        description="Unique identifier for this goal.",
    )

    description: str = Field(
        ...,
        description="Natural-language description of the goal.",
        examples=["Protect the family reputation."],
    )

    priority: int = Field(
        default=50,
        description="Goal priority. Higher values should influence decisions more strongly.",
        ge=0,
        le=100,
    )

    active: bool = Field(
        default=True,
        description="Whether this goal is currently active.",
    )


class GoalManager(BaseModel):
    """
    Manages active, completed, and failed goals for a character.
    """

    active: List[Goal] = Field(
        default_factory=list,
        description="Goals the character is currently pursuing.",
    )

    completed: List[Goal] = Field(
        default_factory=list,
        description="Goals the character has completed.",
    )

    failed: List[Goal] = Field(
        default_factory=list,
        description="Goals the character failed to complete.",
    )

    def add(self, description: str, priority: int = 50) -> Goal:
        goal = Goal(
            description=description,
            priority=priority,
        )

        self.active.append(goal)
        return goal

    def complete(self, goal_id: str) -> None:
        for goal in list(self.active):
            if goal.id == goal_id:
                self.active.remove(goal)
                goal.active = False
                self.completed.append(goal)
                return

        raise AetherValidationError(f"Goal not found: {goal_id}")

    def fail(self, goal_id: str) -> None:
        for goal in list(self.active):
            if goal.id == goal_id:
                self.active.remove(goal)
                goal.active = False
                self.failed.append(goal)
                return

        raise AetherValidationError(f"Goal not found: {goal_id}")

    def prioritize(self) -> List[Goal]:
        return sorted(
            self.active,
            key=lambda goal: goal.priority,
            reverse=True,
        )