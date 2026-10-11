from importlib.metadata import PackageNotFoundError, version

from aether.domain.actions import Action, WorldAction
from aether.domain.character import Character
from aether.domain.events import WorldActionEvent, WorldEvent
from aether.domain.presentation import (
    InteractOptions,
    PresentationCallbacks,
    PresentationChunk,
    PresentationStyle,
    SceneSummary,
)
from aether.domain.sessions import Session
from aether.domain.world import Item, Location, World
from aether.modules.base import AetherModule
from aether.aether import Aether

# Resolve World.sessions forward ref (Session is imported lazily in world.py).
World.model_rebuild()

try:
    __version__ = version("aether-sim")
except PackageNotFoundError:  # pragma: no cover - editable/source tree fallback
    __version__ = "0.1.0"


__all__ = [
    "Action",
    "WorldAction",
    "WorldActionEvent",
    "WorldEvent",
    "AetherModule",
    "Aether",
    "World",
    "Session",
    "Character",
    "Location",
    "Item",
    "PresentationStyle",
    "PresentationCallbacks",
    "PresentationChunk",
    "InteractOptions",
    "SceneSummary",
    "__version__",
]