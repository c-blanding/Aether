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


class UseItemParams(BaseModel):
    item_id: str = Field(
        ...,
        description="ID of the item the actor is attempting to use.",
    )

    target_ids: List[str] = Field(
        default_factory=list,
        description="IDs of entities the item is being used on.",
    )


class UseItemAttributes(BaseModel):
    item_id: str = Field(description="ID of the item that was used.")
    target_ids: List[str] = Field(
        default_factory=list,
        description="IDs of entities the item was used on.",
    )
    used_by_id: str = Field(description="ID of the character that used the item.")
    effect: str = Field(
        default="keep",
        description="keep, consume, or transform.",
    )
    consumed: bool = Field(
        default=False,
        description="Whether the item was removed by this use.",
    )


class PickUpItemParams(BaseModel):
    """
    Parameters for the pick_up_item action.
    """

    item_id: str = Field(
        ...,
        description="ID of the item the actor is attempting to pick up.",
    )


class DropItemParams(BaseModel):
    """
    Parameters for the drop_item action.
    """

    item_id: str = Field(
        ...,
        description="ID of the item the actor is attempting to drop.",
    )


class GiveItemParams(BaseModel):
    """
    Parameters for the give_item action.
    """

    item_id: str = Field(
        ...,
        description="ID of the item the actor is attempting to give.",
    )


class EquipItemParams(BaseModel):
    """Parameters for equipping an owned item."""

    item_id: str = Field(
        ...,
        description="ID of the item the actor is attempting to equip.",
    )
    slot: str = Field(
        default="default",
        description="Equipment slot name (e.g. default, hand, head, body).",
    )


class UnequipItemParams(BaseModel):
    """Parameters for unequipping an item (by id or by slot)."""

    item_id: Optional[str] = Field(
        default=None,
        description="ID of the equipped item to unequip.",
    )
    slot: Optional[str] = Field(
        default=None,
        description="Slot to clear. Provide item_id or slot (or both).",
    )


class ItemPickedUpAttributes(BaseModel):
    """
    Attributes for the item_picked_up event.
    """

    item_id: str = Field(
        ...,
        description="ID of the item that was picked up.",
    )

    previous_location_id: str | None = Field(
        default=None,
        description="Location ID where the item existed before being picked up.",
    )

    new_owner_id: str = Field(
        ...,
        description="Character ID of the new item owner.",
    )


class ItemDroppedAttributes(BaseModel):
    """
    Attributes for the item_dropped event.
    """

    item_id: str = Field(
        ...,
        description="ID of the item that was dropped.",
    )

    previous_owner_id: str = Field(
        ...,
        description="Character ID of the previous item owner.",
    )

    new_location_id: str | None = Field(
        default=None,
        description="Location ID where the item was dropped.",
    )


class ItemGivenAttributes(BaseModel):
    """
    Attributes for the item_given event.
    """

    item_id: str = Field(
        ...,
        description="ID of the item that was given.",
    )

    from_character_id: str = Field(
        ...,
        description="Character ID of the giver.",
    )

    to_character_id: str = Field(
        ...,
        description="Character ID of the receiver.",
    )


class ItemEquippedAttributes(BaseModel):
    item_id: str = Field(..., description="ID of the item that was equipped.")
    character_id: str = Field(..., description="Character who equipped the item.")
    slot: str = Field(..., description="Slot the item was equipped into.")
    previous_item_id: Optional[str] = Field(
        default=None,
        description="Item previously in this slot, if any.",
    )


class ItemUnequippedAttributes(BaseModel):
    item_id: str = Field(..., description="ID of the item that was unequipped.")
    character_id: str = Field(..., description="Character who unequipped the item.")
    slot: str = Field(..., description="Slot the item was removed from.")


class InventoryModule(AetherModule):
    """
    Inventory mechanics module.

    Adds support for:
    - pick_up_item
    - drop_item
    - give_item
    - use_item
    - equip_item
    - unequip_item
    """

    name = "inventory"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        registry.actions.register(
            action_type="pick_up_item",
            module_name=self.name,
            parameter_model=PickUpItemParams,
            handler=self.pick_up_item,
        )
        registry.actions.register(
            action_type="drop_item",
            module_name=self.name,
            parameter_model=DropItemParams,
            handler=self.drop_item,
        )
        registry.actions.register(
            action_type="give_item",
            module_name=self.name,
            parameter_model=GiveItemParams,
            handler=self.give_item,
        )
        registry.actions.register(
            action_type="use_item",
            module_name=self.name,
            parameter_model=UseItemParams,
            handler=self.use_item,
        )
        registry.actions.register(
            action_type="equip_item",
            module_name=self.name,
            parameter_model=EquipItemParams,
            handler=self.equip_item,
        )
        registry.actions.register(
            action_type="unequip_item",
            module_name=self.name,
            parameter_model=UnequipItemParams,
            handler=self.unequip_item,
        )

        registry.events.register(
            event_type="item_picked_up",
            module_name=self.name,
            attribute_model=ItemPickedUpAttributes,
        )
        registry.events.register(
            event_type="item_dropped",
            module_name=self.name,
            attribute_model=ItemDroppedAttributes,
        )
        registry.events.register(
            event_type="item_given",
            module_name=self.name,
            attribute_model=ItemGivenAttributes,
        )
        registry.events.register(
            event_type="item_used",
            module_name=self.name,
            attribute_model=UseItemAttributes,
        )
        registry.events.register(
            event_type="item_equipped",
            module_name=self.name,
            attribute_model=ItemEquippedAttributes,
        )
        registry.events.register(
            event_type="item_unequipped",
            module_name=self.name,
            attribute_model=ItemUnequippedAttributes,
        )

        registry.perceptions.register(
            event_type="item_picked_up",
            module_name=self.name,
            handler=self.perceive_item_picked_up,
        )
        registry.perceptions.register(
            event_type="item_dropped",
            module_name=self.name,
            handler=self.perceive_item_dropped,
        )
        registry.perceptions.register(
            event_type="item_given",
            module_name=self.name,
            handler=self.perceive_item_given,
        )
        registry.perceptions.register(
            event_type="item_used",
            module_name=self.name,
            handler=self.perceive_item_used,
        )
        registry.perceptions.register(
            event_type="item_equipped",
            module_name=self.name,
            handler=self.perceive_item_equipped,
        )
        registry.perceptions.register(
            event_type="item_unequipped",
            module_name=self.name,
            handler=self.perceive_item_unequipped,
        )

    def pick_up_item(self, world: World, action: Action) -> List[WorldEvent]:
        params = PickUpItemParams.model_validate(action.data.parameters)

        actor = world.characters.get(action.actor_id)
        item = world.items.get(params.item_id)

        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")

        if item.state.owner_id is not None:
            raise AetherValidationError("Item is already owned.")

        if actor.state.location_id != item.state.location_id:
            raise AetherValidationError(
                "Actor and item are not in the same location."
            )

        previous_location_id = item.state.location_id

        item.state.owner_id = actor.id
        item.state.location_id = None
        actor.inventory.add(item.id)

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[item.id],
            data=WorldActionEvent(
                type="item_picked_up",
                module="inventory",
                attributes={
                    "item_id": item.id,
                    "previous_location_id": previous_location_id,
                    "new_owner_id": actor.id,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )

        return [event]

    def perceive_item_picked_up(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ItemPickedUpAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(event.actor_id)
        item_name = world.describe_item(attrs.item_id)
        location_ids = [
            location_id
            for location_id in [attrs.previous_location_id]
            if location_id
        ]

        if character_id == attrs.new_owner_id:
            perspective = f"I picked up the {item_name}."
            importance = 0.7
            emotion = "curiosity"
            emotional_weight = 0.3
        else:
            perspective = f"I saw {actor_name} pick up the {item_name}."
            importance = 0.45
            emotion = None
            emotional_weight = 0.1

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} picked up the {item_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["inventory", "item_picked_up", item_name.lower()],
            participant_ids=[
                value
                for value in [event.actor_id, attrs.new_owner_id]
                if value
            ],
            location_ids=location_ids,
        )

    def drop_item(self, world: World, action: Action) -> List[WorldEvent]:
        params = DropItemParams.model_validate(action.data.parameters)

        actor = world.characters.get(action.actor_id)
        item = world.items.get(params.item_id)

        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")

        if item.state.owner_id != actor.id:
            raise AetherValidationError("Actor does not own this item.")

        if actor.inventory.is_equipped(item.id):
            raise AetherValidationError(
                "Item is equipped; unequip it before dropping."
            )

        previous_owner_id = item.state.owner_id

        item.state.owner_id = None
        item.state.location_id = actor.state.location_id
        actor.inventory.remove(item.id)

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[item.id],
            data=WorldActionEvent(
                type="item_dropped",
                module="inventory",
                attributes={
                    "item_id": item.id,
                    "previous_owner_id": previous_owner_id,
                    "new_location_id": actor.state.location_id,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )

        return [event]

    def perceive_item_dropped(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ItemDroppedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(event.actor_id)
        item_name = world.describe_item(attrs.item_id)
        location_ids = [
            location_id
            for location_id in [attrs.new_location_id]
            if location_id
        ]

        if character_id == attrs.previous_owner_id:
            perspective = f"I put down the {item_name}."
            importance = 0.55
            emotion = None
            emotional_weight = 0.1
        else:
            perspective = f"I saw {actor_name} drop the {item_name}."
            importance = 0.4
            emotion = None
            emotional_weight = 0.05

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} dropped the {item_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["inventory", "item_dropped", item_name.lower()],
            participant_ids=[
                value
                for value in [event.actor_id, attrs.previous_owner_id]
                if value
            ],
            location_ids=location_ids,
        )

    def give_item(self, world: World, action: Action) -> List[WorldEvent]:
        params = GiveItemParams.model_validate(action.data.parameters)

        source = world.characters.get(action.actor_id)
        target = world.characters.get(action.target_id or "")
        item = world.items.get(params.item_id)

        if source is None:
            raise AetherValidationError(f"Source actor does not exist: {action.actor_id}")

        if target is None:
            raise AetherValidationError(f"Target actor does not exist: {action.target_id}")

        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")

        if item.state.owner_id != source.id:
            raise AetherValidationError("Source actor does not own this item.")

        if source.inventory.is_equipped(item.id):
            raise AetherValidationError(
                "Item is equipped; unequip it before giving."
            )

        if source.state.location_id != target.state.location_id:
            raise AetherValidationError(
                "Source and target are not in the same location."
            )

        source.inventory.remove(item.id)
        target.inventory.add(item.id)

        item.state.owner_id = target.id
        item.state.location_id = None

        event = WorldEvent(
            world_id=world.id,
            actor_id=source.id,
            target_ids=[target.id, item.id],
            data=WorldActionEvent(
                type="item_given",
                module="inventory",
                attributes={
                    "item_id": item.id,
                    "from_character_id": source.id,
                    "to_character_id": target.id,
                },
            ),
            witnessed_by=world.determine_witnesses(source.id),
        )

        return [event]

    def perceive_item_given(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ItemGivenAttributes.model_validate(event.data.attributes)
        giver_name = world.describe_character(attrs.from_character_id)
        receiver_name = world.describe_character(attrs.to_character_id)
        item_name = world.describe_item(attrs.item_id)

        if character_id == attrs.from_character_id:
            perspective = f"I gave the {item_name} to {receiver_name}."
            importance = 0.75
            emotion = "resolve"
            emotional_weight = 0.35
        elif character_id == attrs.to_character_id:
            perspective = f"{giver_name} gave me the {item_name}."
            importance = 0.8
            emotion = "surprise"
            emotional_weight = 0.45
        else:
            perspective = (
                f"I saw {giver_name} give the {item_name} to {receiver_name}."
            )
            importance = 0.5
            emotion = None
            emotional_weight = 0.15

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=(
                f"{giver_name} gave the {item_name} to {receiver_name}."
            ),
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["inventory", "item_given", item_name.lower()],
            participant_ids=[
                value
                for value in [
                    attrs.from_character_id,
                    attrs.to_character_id,
                ]
                if value
            ],
        )

    def use_item(self, world: World, action: Action) -> List[WorldEvent]:
        params = UseItemParams.model_validate(action.data.parameters)

        actor = world.characters.get(action.actor_id)
        item = world.items.get(params.item_id)

        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")

        if item.state.owner_id != actor.id:
            raise AetherValidationError("Actor does not own this item.")

        if item.state.consumed:
            raise AetherValidationError("Item has already been consumed.")

        if actor.inventory.is_equipped(item.id):
            raise AetherValidationError(
                "Item is equipped; unequip it before using."
            )

        effect = item.use_mode
        consumed = False
        if effect == "consume":
            item.state.owner_id = None
            item.state.location_id = None
            item.state.container_id = None
            item.state.consumed = True
            actor.inventory.remove(item.id)
            consumed = True
        elif effect == "transform":
            if item.transform_name:
                item.name = item.transform_name
            if item.transform_description:
                item.description = item.transform_description
            item.use_mode = "keep"

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[item.id, *params.target_ids],
            data=WorldActionEvent(
                type="item_used",
                module="inventory",
                attributes={
                    "item_id": item.id,
                    "target_ids": params.target_ids,
                    "used_by_id": actor.id,
                    "effect": effect,
                    "consumed": consumed,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )

        return [event]

    def perceive_item_used(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = UseItemAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.used_by_id)
        item_name = world.describe_item(attrs.item_id)

        if character_id == attrs.used_by_id:
            perspective = f"I used the {item_name}."
            importance = 0.7
            emotion = "focus"
            emotional_weight = 0.3
        elif character_id in attrs.target_ids:
            perspective = f"{actor_name} used the {item_name} on me."
            importance = 0.85
            emotion = "alarm"
            emotional_weight = 0.55
        else:
            perspective = f"I saw {actor_name} use the {item_name}."
            importance = 0.5
            emotion = None
            emotional_weight = 0.2

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} used the {item_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["inventory", "item_used", item_name.lower()],
            participant_ids=[
                value
                for value in [attrs.used_by_id, *attrs.target_ids]
                if value
            ],
        )

    def equip_item(self, world: World, action: Action) -> List[WorldEvent]:
        params = EquipItemParams.model_validate(action.data.parameters)

        actor = world.characters.get(action.actor_id)
        item = world.items.get(params.item_id)

        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        if item is None:
            raise AetherValidationError(f"Item does not exist: {params.item_id}")

        if item.state.owner_id != actor.id:
            raise AetherValidationError("Actor does not own this item.")

        if not actor.inventory.contains(item.id):
            raise AetherValidationError("Item is not in the actor's inventory.")

        slot = params.slot.strip() or "default"
        previous_item_id = actor.inventory.equip(item.id, slot=slot)
        witnesses = world.determine_witnesses(actor.id)
        events: List[WorldEvent] = []

        if previous_item_id is not None:
            events.append(
                WorldEvent(
                    world_id=world.id,
                    actor_id=actor.id,
                    target_ids=[previous_item_id],
                    data=WorldActionEvent(
                        type="item_unequipped",
                        module="inventory",
                        attributes={
                            "item_id": previous_item_id,
                            "character_id": actor.id,
                            "slot": slot,
                        },
                    ),
                    witnessed_by=witnesses,
                )
            )

        events.append(
            WorldEvent(
                world_id=world.id,
                actor_id=actor.id,
                target_ids=[item.id],
                data=WorldActionEvent(
                    type="item_equipped",
                    module="inventory",
                    attributes={
                        "item_id": item.id,
                        "character_id": actor.id,
                        "slot": slot,
                        "previous_item_id": previous_item_id,
                    },
                ),
                witnessed_by=witnesses,
            )
        )

        return events

    def perceive_item_equipped(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ItemEquippedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.character_id)
        item_name = world.describe_item(attrs.item_id)

        if character_id == attrs.character_id:
            perspective = f"I equipped the {item_name}."
            importance = 0.55
            emotion = None
            emotional_weight = 0.15
        else:
            perspective = f"I saw {actor_name} equip the {item_name}."
            importance = 0.35
            emotion = None
            emotional_weight = 0.05

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} equipped the {item_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["inventory", "item_equipped", item_name.lower(), attrs.slot],
            participant_ids=[attrs.character_id],
        )

    def unequip_item(self, world: World, action: Action) -> List[WorldEvent]:
        params = UnequipItemParams.model_validate(action.data.parameters)

        actor = world.characters.get(action.actor_id)
        if actor is None:
            raise AetherValidationError(f"Actor does not exist: {action.actor_id}")

        item_id = params.item_id
        slot = params.slot.strip() if params.slot else None

        if not item_id and not slot:
            raise AetherValidationError(
                "Provide item_id or slot to unequip."
            )

        if slot and item_id:
            equipped_in_slot = actor.inventory.equipped.get(slot)
            if equipped_in_slot != item_id:
                raise AetherValidationError(
                    f"Item {item_id} is not equipped in slot '{slot}'."
                )
        elif slot:
            item_id = actor.inventory.equipped.get(slot)
            if item_id is None:
                raise AetherValidationError(f"Nothing equipped in slot '{slot}'.")
        else:
            slot = actor.inventory.slot_of(item_id)
            if slot is None:
                raise AetherValidationError("Item is not equipped.")

        cleared = actor.inventory.unequip_slot(slot)
        if cleared is None or cleared != item_id:
            raise AetherValidationError("Failed to unequip item.")

        event = WorldEvent(
            world_id=world.id,
            actor_id=actor.id,
            target_ids=[item_id],
            data=WorldActionEvent(
                type="item_unequipped",
                module="inventory",
                attributes={
                    "item_id": item_id,
                    "character_id": actor.id,
                    "slot": slot,
                },
            ),
            witnessed_by=world.determine_witnesses(actor.id),
        )

        return [event]

    def perceive_item_unequipped(
        self,
        world: World,
        character_id: str,
        event: WorldEvent,
    ) -> Optional[Perception]:
        attrs = ItemUnequippedAttributes.model_validate(event.data.attributes)
        actor_name = world.describe_character(attrs.character_id)
        item_name = world.describe_item(attrs.item_id)

        if character_id == attrs.character_id:
            perspective = f"I unequipped the {item_name}."
            importance = 0.45
            emotion = None
            emotional_weight = 0.1
        else:
            perspective = f"I saw {actor_name} unequip the {item_name}."
            importance = 0.3
            emotion = None
            emotional_weight = 0.05

        return Perception(
            character_id=character_id,
            event_id=event.id,
            summary=f"{actor_name} unequipped the {item_name}.",
            perspective=perspective,
            importance=importance,
            emotional_weight=emotional_weight,
            emotion=emotion,
            tags=["inventory", "item_unequipped", item_name.lower(), attrs.slot],
            participant_ids=[attrs.character_id],
        )