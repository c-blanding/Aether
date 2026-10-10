from pydantic import BaseModel, Field




class ItemState(BaseModel):
    location_id: str | None = None
    owner_id: str | None = None

    def is_owned(self) -> bool:
        return self.owner_id is not None

    def is_in_location(self) -> bool:
        return self.location_id is not None


class Item(BaseModel):
    id: str = Field(default_factory=lambda: new_id("item"))

    name: str
    description: str = ""
    state: ItemState = Field(default_factory=ItemState)


class WorldState(BaseModel):
    version: int = 0
    active_session_ids: list[str] = Field(default_factory=list)

    def increment_version(self) -> None:
        self.version += 1
