from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from aether.domain.actions import Action
from aether.domain.character import Character
from aether.domain.interactions import DialogueLine, Interaction
from aether.modules.base import AetherModule
from aether.components.shared import AetherValidationError
from aether.domain.world import World, WorldMetadata
from aether.engine.runtime_engine import RuntimeEngine


class Runtime:
    """
    AI orchestration placeholder.

    Later this owns LangGraph, retrieval, prompting, structured output,
    and generation.
    """

    def interpret(self, message: str, actor_id: str = "player") -> list[Action]:
        return []

    def generate_dialogue(
        self,
        character: Character,
        interaction: Interaction,
    ) -> list[DialogueLine]:
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


class ProviderRegistry:
    """
    Registry for external providers such as LLMs, image models, and voice models.
    """

    def __init__(self) -> None:
        self.llm_providers: dict[str, Any] = {}
        self.image_providers: dict[str, Any] = {}
        self.voice_providers: dict[str, Any] = {}


class Aether:
    """
     AI simulation SDK for building persistent, intelligent characters and evolving interactive worlds.
    """

    def __init__(self) -> None:
        self.engine = RuntimeEngine()
        self.worlds: dict[str, World] = {}
        self.runtime = Runtime()
        self.providers = ProviderRegistry()
        self.configuration = AetherConfig()

    def create_world(
        self,
        name: str,
        description: str = "",
    ) -> World:
        world = World(
            metadata=WorldMetadata(
                name=name,
                description=description,
            ),
            engine=self.engine,
        )
        self.worlds[world.id] = world
        return world

           ## Modules to use in the world
    def use(self, *modules: AetherModule) -> Aether:
        for module in modules:
            self.engine.register_module(module)
        
        return self

    def get_world(self, world_id: str) -> World:
        world = self.worlds.get(world_id)

        if world is None:
            raise AetherValidationError(f"World not found: {world_id}")

        return world

    def delete_world(self, world_id: str) -> None:
        self.worlds.pop(world_id, None)
