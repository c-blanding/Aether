from pydantic import BaseModel, Field


class Inventory(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    capacity: int | None = None
    equipped: dict[str, str] = Field(
        default_factory=dict,
        description="Map of equipment slot name to currently equipped item ID.",
    )

    def add(self, item_id: str) -> None:
        if self.capacity is not None and len(self.item_ids) >= self.capacity:
            raise ValueError("Inventory is full.")

        if item_id not in self.item_ids:
            self.item_ids.append(item_id)

    def remove(self, item_id: str) -> None:
        if item_id in self.item_ids:
            self.item_ids.remove(item_id)
        self.unequip_item(item_id)

    def contains(self, item_id: str) -> bool:
        return item_id in self.item_ids

    def is_equipped(self, item_id: str) -> bool:
        return item_id in self.equipped.values()

    def slot_of(self, item_id: str) -> str | None:
        for slot, equipped_id in self.equipped.items():
            if equipped_id == item_id:
                return slot
        return None

    def equip(self, item_id: str, slot: str = "default") -> str | None:
        """
        Equip an owned item into a slot.

        Returns the previously equipped item ID in that slot, if any.
        """
        if item_id not in self.item_ids:
            raise ValueError("Item is not in inventory.")

        previous = self.equipped.get(slot)
        # An item can only occupy one slot.
        existing_slot = self.slot_of(item_id)
        if existing_slot is not None:
            del self.equipped[existing_slot]

        self.equipped[slot] = item_id
        return previous if previous != item_id else None

    def unequip_slot(self, slot: str) -> str | None:
        return self.equipped.pop(slot, None)

    def unequip_item(self, item_id: str) -> str | None:
        slot = self.slot_of(item_id)
        if slot is None:
            return None
        del self.equipped[slot]
        return slot
