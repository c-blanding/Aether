from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from aether.modules.detective import DetectiveModule as DetectiveModule
    from aether.modules.dialogue import DialogueModule as DialogueModule
    from aether.modules.inventory import InventoryModule as InventoryModule
    from aether.modules.navigation import NavigationModule as NavigationModule
    from aether.modules.social import SocialModule as SocialModule

__all__ = [
    "InventoryModule",
    "NavigationModule",
    "DialogueModule",
    "DetectiveModule",
    "SocialModule",
]


def __getattr__(name: str):
    if name == "InventoryModule":
        from aether.modules.inventory import InventoryModule

        return InventoryModule
    if name == "NavigationModule":
        from aether.modules.navigation import NavigationModule

        return NavigationModule
    if name == "DialogueModule":
        from aether.modules.dialogue import DialogueModule

        return DialogueModule
    if name == "DetectiveModule":
        from aether.modules.detective import DetectiveModule

        return DetectiveModule
    if name == "SocialModule":
        from aether.modules.social import SocialModule

        return SocialModule
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
