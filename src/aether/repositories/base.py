from __future__ import annotations

from aether.components.shared import AetherError


class RepositoryError(AetherError):
    """Base error for repository operations."""


class NotFoundError(RepositoryError):
    """Raised when an entity cannot be found in a repository."""


class DuplicateError(RepositoryError):
    """Raised when an append-only store already contains the entity ID."""
