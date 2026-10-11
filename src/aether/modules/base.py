from abc import ABC, abstractmethod

from aether.engine.registries import ModuleRegistry


class AetherModule(ABC):
    """
    Abstract base for world modules.

    Modules register action schemas, event schemas, and action handlers
    via ``register``.
    """

    name: str
    version: str = "0.1.0"

    @abstractmethod
    def register(self, registry: ModuleRegistry) -> None:
        ...
