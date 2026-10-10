from pydantic import BaseModel, Field


class Inventory(BaseModel):
    item_ids: list[str] = Field(default_factory=list)
    capacity: int | None = None

    def add(self, item_id: str) -> None:
        if self.capacity is not None and len(self.item_ids) >= self.capacity:
            raise ValueError("Inventory is full.")

        if item_id not in self.item_ids:
            self.item_ids.append(item_id)

    def remove(self, item_id: str) -> None:
        if item_id in self.item_ids:
            self.item_ids.remove(item_id)

    def contains(self, item_id: str) -> bool:
        return item_id in self.item_ids