from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aether.modules.inventory import InventoryModule as InventoryModule

__all__ = [
    "InventoryModule",
]


def __getattr__(name: str):
    if name == "InventoryModule":
        from aether.modules.inventory import InventoryModule

        return InventoryModule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
