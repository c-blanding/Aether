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

    def allows(self, capability: str) -> bool:
        return capability in self.capabilities