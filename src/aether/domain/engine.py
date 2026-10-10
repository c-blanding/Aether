from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from aether.domain.actions import Action
from aether.domain.character import Character
from aether.domain.interactions import DialogueLine, Interaction
from aether.components.shared import AetherValidationError
from aether.domain.world import World, WorldMetadata


class Runtime(BaseModel):
    """
    AI orchestration placeholder.

    Later this owns LangGraph, retrieval, prompting, structured output,
    and generation.
    """

    def interpret(self, message: str, actor_id: str = "player") -> List[Action]:
        return []

    def generate_dialogue(
        self,
        character: Character,
        interaction: Interaction,
    ) -> List[DialogueLine]:
        return []


class AetherConfig(BaseModel):
    """
    Configuration for the Aether SDK runtime.
    """

    environment: str = Field(
        default="development",
        description="Runtime environment name.",
        examples=["development", "staging", "production"],
    )

    debug: bool = Field(
        default=True,
        description="Whether debug mode is enabled.",
    )



class ProviderRegistry(BaseModel):
    """
    Registry for external providers such as LLMs, image models, and voice models.
    """

    llm_providers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of LLM provider name to provider client/configuration.",
    )

    image_providers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of image provider name to provider client/configuration.",
    )

    voice_providers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping of voice provider name to provider client/configuration.",
    )


class Aether(BaseModel):
    """
    Root SDK object.

    Developers start here.
    """

    worlds: Dict[str, World] = Field(
        default_factory=dict,
        description="Mapping of world ID to World aggregate.",
    )

    runtime: Runtime = Field(
        default_factory=Runtime,
        description="AI runtime responsible for interpretation and generation.",
    )

    providers: ProviderRegistry = Field(
        default_factory=ProviderRegistry,
        description="Registry of external model and media providers.",
    )

    configuration: AetherConfig = Field(
        default_factory=AetherConfig,
        description="SDK-level runtime configuration.",
    )

    def create_world(
        self,
        name: str,
        description: str = "",
    ) -> World:
        world = World(
            metadata=WorldMetadata(
                name=name,
                description=description,
            )
        )

        self.worlds[world.id] = world
        return world

    def get_world(self, world_id: str) -> World:
        world = self.worlds.get(world_id)

        if world is None:
            raise AetherValidationError(f"World not found: {world_id}")

        return world

    def delete_world(self, world_id: str) -> None:
        self.worlds.pop(world_id, None)