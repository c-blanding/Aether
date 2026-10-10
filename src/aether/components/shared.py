from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


def new_id(prefix: str) -> str:
    """
    Create a readable unique ID with a stable prefix.
    """
    return f"{prefix}_{uuid4().hex[:12]}"


def utc_now() -> datetime:
    """
    Return the current UTC datetime.
    """
    return datetime.now(timezone.utc)


class AetherError(Exception):
    """
    Base exception for all Aether-specific errors.
    """


class AetherValidationError(AetherError):
    """
    Raised when a model, action, event, or domain rule is invalid.
    """


class UnknownActionError(AetherValidationError):
    """
    Raised when an action type has not been registered.
    """


class UnknownEventError(AetherValidationError):
    """
    Raised when an event type has not been registered.
    """


class ModuleNotFoundError(AetherError):
    """
    Raised when a requested Aether module is not installed on a world.
    """