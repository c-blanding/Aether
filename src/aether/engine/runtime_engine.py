from __future__ import annotations

from typing import TYPE_CHECKING

from aether.engine.registries import AetherModule, ModuleRegistry

if TYPE_CHECKING:
    from aether.domain.actions import Action
    from aether.domain.events import WorldEvent
    from aether.domain.world import World


class RuntimeEngine:
    """Executes validated world actions through installed modules."""

    def __init__(self) -> None:
        self.modules = ModuleRegistry()

    def register_module(self, module: AetherModule) -> None:
        self.modules.register(module)

    def execute(self, world: World, action: Action) -> list[WorldEvent]:
        validated = self.modules.actions.validate(action)

        handler = self.modules.actions.get_handler(validated.type)

        events = handler(world, validated)

        validated_events = [
            self.modules.events.validate(event)
            for event in events
        ]

        world.events.append_many(validated_events)
        world.state.increment_version()

        return validated_events
