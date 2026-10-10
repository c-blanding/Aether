from __future__ import annotations

from pydantic import BaseModel, Field

from aether.engine.registries import ModuleRegistry
from aether.modules.base import AetherModule


class MoveParameters(BaseModel):
    actor_id: str = Field(..., description="ID of the actor attempting to move.")
    destination_location_id: str = Field(
        ...,
        description="ID of the location to move to.",
    )


class NavigationModule(AetherModule):
    """Navigation mechanics module (stub)."""

    name = "navigation"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        pass
