from __future__ import annotations

from typing import TYPE_CHECKING

from aether.components.shared import AetherValidationError
from aether.engine.registries import ModuleRegistry

if TYPE_CHECKING:
    from aether.domain.actions import Action
    from aether.domain.events import WorldEvent
    from aether.domain.world import World
    from aether.modules.base import AetherModule


class RuntimeEngine:
    """Executes validated world actions through installed modules."""

    def __init__(self) -> None:
        self.modules = ModuleRegistry()

    def register_module(self, module: AetherModule) -> None:
        self.modules.register(module)

    def execute(self, world: World, action: Action) -> list[WorldEvent]:
        validated = self.modules.actions.validate(action)
        self._enforce_capabilities(world, validated)

        handler = self.modules.actions.get_handler(validated.type)

        events = handler(world, validated)

        validated_events = [
            self.modules.events.validate(event)
            for event in events
        ]

        world.events.append_many(validated_events)
        world.state.increment_version()

        return validated_events

    def _enforce_capabilities(self, world: World, action: Action) -> None:
        """
        Reject actions when the actor has a non-empty capability set that
        does not include the action's required capability.

        Empty capability set = unrestricted (backward compatible).
        """
        actor = world.characters.get(action.actor_id)
        if actor is None:
            # Let module handlers raise a clearer actor-missing error.
            return

        if actor.capabilities.is_unrestricted():
            return

        registration = self.modules.actions.get(action.type)
        required = registration.required_capability
        if not actor.capabilities.allows(required):
            raise AetherValidationError(
                f"Actor '{action.actor_id}' lacks capability '{required}' "
                f"required for action '{action.type}'."
            )

    def list_action_types(self) -> list[str]:
        return self.modules.actions.action_types()
