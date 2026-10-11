from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from aether.components.shared import new_id


class WorldAction(BaseModel):
    """
    Modular action data.

    Represents the specific command or mechanic an actor is attempting.
    """

    type: str = Field(
        ...,
        description="The action type being attempted, such as 'pick_up_item', 'speak', or 'present_evidence'.",
        examples=["pick_up_item"],
    )

    module: Optional[str] = Field(
        default=None,
        description="The module responsible for handling this action, such as 'inventory', 'dialogue', or 'detective'.",
        examples=["inventory"],
    )

    version: int = Field(
        default=1,
        description="Version number for the action schema. Useful when modules evolve over time.",
        ge=1,
    )

    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific input parameters validated by the module's registered action schema.",
        examples=[{"item_id": "item_old_key"}],
    )


class Action(BaseModel):
    """
    A concrete attempted action inside a world.

    Actions are attempts. They must be validated and handled before becoming events.
    """

    id: str = Field(
        default_factory=lambda: new_id("act"),
        description="Unique identifier for this attempted action.",
        examples=["act_abc123"],
    )

    actor_id: str = Field(
        ...,
        description="ID of the character or player attempting the action.",
        examples=["char_player"],
    )

    target_id: Optional[str] = Field(
        default=None,
        description="Primary target of the action, if there is one.",
        examples=["item_old_key"],
    )

    target_ids: List[str] = Field(
        default_factory=list,
        description="Additional targets affected by the action.",
        examples=[["char_arthur", "item_old_key"]],
    )

    data: WorldAction = Field(
        ...,
        description="Modular action payload containing the action type, module, version, and parameters.",
    )

    witnesses: List[str] = Field(
        default_factory=list,
        description="IDs of characters that witnessed the action.",
        examples=["char_arthur", "char_bob"],
    )

    @property
    def type(self) -> str:
        return self.data.type

    @property
    def module(self) -> Optional[str]:
        return self.data.module