from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable, Type

from pydantic import BaseModel

from aether.domain.actions import Action
from aether.domain.events import WorldEvent
from aether.components.shared import (
    AetherValidationError,
    ModuleNotFoundError,
    UnknownActionError,
    UnknownEventError,
)


ActionHandler = Callable[[Any, Action], list[WorldEvent]]


@dataclass
class RegisteredAction:
    """Registered action definition contributed by an Aether module."""

    action_type: str
    module_name: str
    parameter_model: Type[BaseModel]
    handler: ActionHandler


class ActionRegistry:
    """Registry for validating and routing modular world actions."""

    def __init__(self) -> None:
        self.actions: dict[str, RegisteredAction] = {}

    def register(
        self,
        action_type: str,
        module_name: str,
        parameter_model: Type[BaseModel],
        handler: ActionHandler,
    ) -> None:
        self.actions[action_type] = RegisteredAction(
            action_type=action_type,
            module_name=module_name,
            parameter_model=parameter_model,
            handler=handler,
        )

    def validate(self, action: Action) -> Action:
        registration = self.actions.get(action.type)

        if registration is None:
            raise UnknownActionError(f"Unknown action type: {action.type}")

        validated_parameters = registration.parameter_model.model_validate(
            action.data.parameters
        )

        validated_data = action.data.model_copy(
            update={
                "module": action.data.module or registration.module_name,
                "parameters": validated_parameters.model_dump(),
            }
        )

        return action.model_copy(
            update={
                "data": validated_data,
            }
        )

    def get_handler(self, action_type: str) -> ActionHandler:
        registration = self.actions.get(action_type)

        if registration is None:
            raise UnknownActionError(f"Unknown action type: {action_type}")

        return registration.handler

    def supports(self, action_type: str) -> bool:
        return action_type in self.actions


@dataclass
class RegisteredEventSchema:
    """Registered event schema contributed by an Aether module."""

    event_type: str
    module_name: str
    attribute_model: Type[BaseModel]


class EventRegistry:
    """Registry for validating modular world event attributes."""

    def __init__(self) -> None:
        self.events: dict[str, RegisteredEventSchema] = {}

    def register(
        self,
        event_type: str,
        module_name: str,
        attribute_model: Type[BaseModel],
    ) -> None:
        self.events[event_type] = RegisteredEventSchema(
            event_type=event_type,
            module_name=module_name,
            attribute_model=attribute_model,
        )

    def validate(self, event: WorldEvent) -> WorldEvent:
        registration = self.events.get(event.type)

        if registration is None:
            raise UnknownEventError(f"Unknown event type: {event.type}")

        validated_attributes = registration.attribute_model.model_validate(
            event.data.attributes
        )

        validated_data = event.data.model_copy(
            update={
                "module": event.data.module or registration.module_name,
                "attributes": validated_attributes.model_dump(),
            }
        )

        return event.model_copy(
            update={
                "data": validated_data,
            }
        )

    def supports(self, event_type: str) -> bool:
        return event_type in self.events


# Backward-compatible alias
EventSchemaRegistry = EventRegistry


class ModuleRegistry:
    """
    Registry of installed modules.

    Owns the action and event registries.
    """

    def __init__(self) -> None:
        self.modules: dict[str, AetherModule] = {}
        self.actions = ActionRegistry()
        self.events = EventRegistry()
        self.perceptions = Perception

    def register(self, module: AetherModule) -> None:
        name = getattr(module, "name", None)
        if not name:
            raise AetherValidationError(
                f"{type(module).__name__} must define a non-empty 'name' class attribute."
            )
        self.modules[name] = module
        module.register(self)

    def get(self, module_name: str) -> AetherModule:
        module = self.modules.get(module_name)

        if module is None:
            raise ModuleNotFoundError(f"Module not registered: {module_name}")

        return module

    def is_installed(self, module_name: str) -> bool:
        return module_name in self.modules



from typing import Callable, Dict, Optional

from aether.events import WorldEvent
from aether.cognition.perception import Perception


PerceptionHandler = Callable[
    ["World", str, WorldEvent],
    Optional[Perception],
]


class PerceptionRegistry:
    """
    Registry that maps event types to perception handlers.
    """

    def __init__(self) -> None:
        self.handlers: Dict[str, PerceptionHandler] = {}

    def register(
        self,
        event_type: str,
        handler: PerceptionHandler,
    ) -> None:
        self.handlers[event_type] = handler

    def get(
        self,
        event_type: str,
    ) -> Optional[PerceptionHandler]:
        return self.handlers.get(event_type)

    def supports(
        self,
        event_type: str,
    ) -> bool:
        return event_type in self.handlers


