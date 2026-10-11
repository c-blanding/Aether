from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from aether.cognition.perception import Perception
from aether.components.shared import AetherValidationError
from aether.domain.actions import Action
from aether.domain.events import WorldActionEvent, WorldEvent
from aether.domain.world import World
from aether.engine.registries import ModuleRegistry
from aether.modules.base import AetherModule


class ContainerItemParams(BaseModel):
    item_id: str = Field(..., description="ID of the item being moved.")
    container_id: str = Field(..., description="ID of the container item.")


class ContainerOnlyParams(BaseModel):
    container_id: str = Field(..., description="ID of the container item.")


class ContainerTransferAttributes(BaseModel):
    item_id: str
    container_id: str
    actor_id: str


class ContainerStateAttributes(BaseModel):
    container_id: str
    actor_id: str
    container_open: bool


class ContainerModule(AetherModule):
    """Put items into containers and take them back out."""

    name = "containers"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        registry.actions.register(
            action_type="put_in",
            module_name=self.name,
            parameter_model=ContainerItemParams,
            handler=self.put_in,
        )
        registry.actions.register(
            action_type="take_from",
            module_name=self.name,
            parameter_model=ContainerItemParams,
            handler=self.take_from,
        )
        registry.actions.register(
            action_type="open_container",
            module_name=self.name,
            parameter_model=ContainerOnlyParams,
            handler=self.open_container,
        )
        registry.actions.register(
            action_type="close_container",
            module_name=self.name,
            parameter_model=ContainerOnlyParams,
            handler=self.close_container,
        )

        for event_type in ("item_put_in", "item_taken_from"):
            registry.events.register(
                event_type=event_type,
                module_name=self.name,
                attribute_model=ContainerTransferAttributes,
            )
        for event_type in ("container_opened", "container_closed"):
            registry.events.register(
                event_type=event_type,
                module_name=self.name,
                attribute_model=ContainerStateAttributes,
            )

        registry.perceptions.register(
            event_type="item_put_in",
            module_name=self.name,
            handler=self.perceive_transfer,
        )
        registry.perceptions.register(
            event_type="item_taken_from",
            module_name=self.name,
            handler=self.perceive_transfer,
        )
        registry.perceptions.register(
            event_type="container_opened",
            module_name=self.name,
            handler=self.perceive_container_state,
        )
        registry.perceptions.register(
            event_type="container_closed",
            module_name=self.name,
            handler=self.perceive_container_state,
        )

    def _actor_at_container(self, world: World, actor_id: str, container_id: str):
        actor = world.characters.get(actor_id)
        container = world.items.get(container_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {actor_id}")
        if container is None or not container.is_container:
            raise AetherValidationError(f"Container does not exist: {container_id}")
        if container.state.consumed:
            raise AetherValidationError("Container has been consumed.")
        here = actor.state.location_id
        accessible = container.state.location_id == here or container.state.owner_id == actor.id
        if not accessible:
            raise AetherValidationError("Actor cannot reach that container.")
        return actor, container

    def open_container(self, world: World, action: Action) -> List[WorldEvent]:
        params = ContainerOnlyParams.model_validate(action.data.parameters)
        actor, container = self._actor_at_container(
            world, action.actor_id, params.container_id
        )
        if container.container_open:
            raise AetherValidationError("Container is already open.")
        container.container_open = True
        return [
            self._state_event(world, actor.id, container.id, True, "container_opened")
        ]

    def close_container(self, world: World, action: Action) -> List[WorldEvent]:
        params = ContainerOnlyParams.model_validate(action.data.parameters)
        actor, container = self._actor_at_container(
            world, action.actor_id, params.container_id
        )
        if not container.container_open:
            raise AetherValidationError("Container is already closed.")
        container.container_open = False
        return [
            self._state_event(world, actor.id, container.id, False, "container_closed")
        ]

    def put_in(self, world: World, action: Action) -> List[WorldEvent]:
        params = ContainerItemParams.model_validate(action.data.parameters)
        actor, container = self._actor_at_container(
            world, action.actor_id, params.container_id
        )
        item = world.items.get(params.item_id)
        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")
        if item.id == container.id:
            raise AetherValidationError("A container cannot be placed inside itself.")
        if not container.container_open:
            raise AetherValidationError("Container is closed.")
        if item.state.owner_id != actor.id:
            raise AetherValidationError("Actor does not own this item.")
        if actor.inventory.is_equipped(item.id):
            raise AetherValidationError("Item is equipped; unequip it before storing it.")

        actor.inventory.remove(item.id)
        item.state.owner_id = None
        item.state.location_id = None
        item.state.container_id = container.id
        return [self._transfer_event(world, actor.id, item.id, container.id, "item_put_in")]

    def take_from(self, world: World, action: Action) -> List[WorldEvent]:
        params = ContainerItemParams.model_validate(action.data.parameters)
        actor, container = self._actor_at_container(
            world, action.actor_id, params.container_id
        )
        item = world.items.get(params.item_id)
        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")
        if item.state.container_id != container.id:
            raise AetherValidationError("Item is not inside that container.")
        if not container.container_open:
            raise AetherValidationError("Container is closed.")

        item.state.container_id = None
        item.state.location_id = None
        item.state.owner_id = actor.id
        item.hidden = False
        actor.inventory.add(item.id)
        return [
            self._transfer_event(
                world, actor.id, item.id, container.id, "item_taken_from"
            )
        ]

    def _transfer_event(
        self,
        world: World,
        actor_id: str,
        item_id: str,
        container_id: str,
        event_type: str,
    ) -> WorldEvent:
        return WorldEvent(
            world_id=world.id,
            actor_id=actor_id,
            target_ids=[item_id, container_id],
            data=WorldActionEvent(
                type=event_type,
                module="containers",
                attributes={
                    "item_id": item_id,
                    "container_id": container_id,
                    "actor_id": actor_id,
                },
            ),
            witnessed_by=world.determine_witnesses(actor_id),
        )

    def _state_event(
        self,
        world: World,
        actor_id: str,
        container_id: str,
        container_open: bool,
        event_type: str,
    ) -> WorldEvent:
        return WorldEvent(
            world_id=world.id,
            actor_id=actor_id,
            target_ids=[container_id],
            data=WorldActionEvent(
                type=event_type,
                module="containers",
                attributes={
                    "container_id": container_id,
                    "actor_id": actor_id,
                    "container_open": container_open,
                },
            ),
            witnessed_by=world.determine_witnesses(actor_id),
        )

    def perceive_transfer(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ContainerTransferAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.actor_id)
        item_name = world.describe_item(attrs.item_id)
        container_name = world.describe_item(attrs.container_id)
        stored = event.type == "item_put_in"
        verb = "put" if stored else "took"
        preposition = "into" if stored else "from"
        if character_id == attrs.actor_id:
            perspective = (
                f"I {verb} the {item_name} {preposition} the {container_name}."
            )
            importance = 0.65
        else:
            perspective = (
                f"I saw {actor_name} {verb} the {item_name} "
                f"{preposition} the {container_name}."
            )
            importance = 0.45
        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=(
                f"{actor_name} {verb} the {item_name} {preposition} the {container_name}."
            ),
            perspective=perspective,
            importance=importance,
            emotional_weight=0.15,
            tags=["container", event.type, item_name.lower()],
            participant_ids=[attrs.actor_id],
        )

    def perceive_container_state(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ContainerStateAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.actor_id)
        container_name = world.describe_item(attrs.container_id)
        verb = "opened" if attrs.container_open else "closed"
        if character_id == attrs.actor_id:
            perspective = f"I {verb} the {container_name}."
            importance = 0.5
        else:
            perspective = f"I saw {actor_name} {verb} the {container_name}."
            importance = 0.35
        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} {verb} the {container_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=0.1,
            tags=["container", event.type],
            participant_ids=[attrs.actor_id],
        )
