from __future__ import annotations

from typing import Any, Callable, Dict, List, Type

from pydantic import BaseModel, ConfigDict, Field

from aether.domain.actions import Action
from aether.domain.events import WorldEvent
from aether.components.shared import (
    AetherValidationError,
    ModuleNotFoundError,
    UnknownActionError,
    UnknownEventError,
)


ActionHandler = Callable[[Any, Action], List[WorldEvent]]


class RegisteredAction(BaseModel):
    """
    Registered action definition contributed by an Aether module.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    action_type: str = Field(
        ...,
        description="Unique action type registered by a module.",
        examples=["pick_up_item"],
    )

    module_name: str = Field(
        ...,
        description="Name of the module that registered this action.",
        examples=["inventory"],
    )

    parameter_model: Type[BaseModel] = Field(
        ...,
        description="Pydantic model used to validate this action's parameters.",
    )

    handler: ActionHandler = Field(
        ...,
        description="Callable that handles this action and returns confirmed world events.",
    )


class ActionRegistry(BaseModel):
    """
    Registry for validating and routing modular world actions.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    actions: Dict[str, RegisteredAction] = Field(
        default_factory=dict,
        description="Mapping of action type to registered action definition.",
    )

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


class RegisteredEventSchema(BaseModel):
    """
    Registered event schema contributed by an Aether module.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    event_type: str = Field(
        ...,
        description="Unique event type registered by a module.",
        examples=["item_picked_up"],
    )

    module_name: str = Field(
        ...,
        description="Name of the module that registered this event schema.",
        examples=["inventory"],
    )

    attribute_model: Type[BaseModel] = Field(
        ...,
        description="Pydantic model used to validate this event's attributes.",
    )


class EventSchemaRegistry(BaseModel):
    """
    Registry for validating modular world event attributes.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    events: Dict[str, RegisteredEventSchema] = Field(
        default_factory=dict,
        description="Mapping of event type to registered event schema.",
    )

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


class AetherModule(BaseModel):
    """
    Base class for all world modules.

    Modules register action schemas, event schemas, and action handlers.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str = Field(
        ...,
        description="Unique module name.",
        examples=["inventory"],
    )

    version: str = Field(
        default="0.1.0",
        description="Semantic version for this module.",
    )

    action_schemas: Dict[str, Type[BaseModel]] = Field(
        default_factory=dict,
        description="Mapping of action type to Pydantic parameter schema.",
    )

    event_schemas: Dict[str, Type[BaseModel]] = Field(
        default_factory=dict,
        description="Mapping of event type to Pydantic attribute schema.",
    )

    action_handlers: Dict[str, ActionHandler] = Field(
        default_factory=dict,
        description="Mapping of action type to handler callable.",
    )

    def supports_action(self, action_type: str) -> bool:
        return action_type in self.action_handlers


class ModuleRegistry(BaseModel):
    """
    Registry of installed modules for a world.

    The module registry owns the action and event registries.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    modules: Dict[str, AetherModule] = Field(
        default_factory=dict,
        description="Mapping of module name to installed module.",
    )

    actions: ActionRegistry = Field(
        default_factory=ActionRegistry,
        description="Registry of action schemas and handlers contributed by modules.",
    )

    events: EventSchemaRegistry = Field(
        default_factory=EventSchemaRegistry,
        description="Registry of event schemas contributed by modules.",
    )

    def register(self, module: AetherModule) -> None:
        self.modules[module.name] = module

        for action_type, parameter_model in module.action_schemas.items():
            handler = module.action_handlers.get(action_type)

            if handler is None:
                raise AetherValidationError(
                    f"Module '{module.name}' registered action "
                    f"'{action_type}' without a handler."
                )

            self.actions.register(
                action_type=action_type,
                module_name=module.name,
                parameter_model=parameter_model,
                handler=handler,
            )

        for event_type, attribute_model in module.event_schemas.items():
            self.events.register(
                event_type=event_type,
                module_name=module.name,
                attribute_model=attribute_model,
            )

    def get(self, module_name: str) -> AetherModule:
        module = self.modules.get(module_name)

        if module is None:
            raise ModuleNotFoundError(f"Module not registered: {module_name}")

        return module

    def is_installed(self, module_name: str) -> bool:
        return module_name in self.modules