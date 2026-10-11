from typing import Set

from pydantic import BaseModel, Field


class CapabilitySet(BaseModel):
    """
    Set of capabilities this character can perform.
    """

    capabilities: Set[str] = Field(
        default_factory=set,
        description="Named capabilities available to this character.",
        examples=[["speak", "move", "give_item"]],
    )

    def add(self, capability: str) -> None:
        self.capabilities.add(capability)

    def remove(self, capability: str) -> None:
        self.capabilities.discard(capability)

    def is_unrestricted(self) -> bool:
        """Empty capability set means no restrictions (backward compatible)."""
        return len(self.capabilities) == 0

    def allows(self, capability: str) -> bool:
        if self.is_unrestricted():
            return True
        return capability in self.capabilities