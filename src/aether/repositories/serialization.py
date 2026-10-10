from __future__ import annotations

from typing import Any

from aether.components.planner import Planner
from aether.domain.character import Character
from aether.domain.events import WorldEvent
from aether.domain.sessions import Session
from aether.domain.world import World


def serialize_world(world: World) -> dict[str, Any]:
    """JSON-ready World payload (excludes non-persistent runtime engine)."""
    return world.model_dump(mode="json", exclude={"engine"})


def deserialize_world(data: dict[str, Any]) -> World:
    return World.model_validate(data)


def serialize_character(character: Character) -> dict[str, Any]:
    data = character.model_dump(mode="json", exclude={"planner"})
    data["planner"] = {"strategy": getattr(character.planner, "strategy", "goal_driven")}
    return data


def deserialize_character(data: dict[str, Any]) -> Character:
    payload = dict(data)
    planner_data = payload.get("planner")
    if isinstance(planner_data, Planner):
        planner = planner_data
    else:
        planner_data = planner_data or {}
        planner = Planner(strategy=planner_data.get("strategy", "goal_driven"))
    payload["planner"] = planner
    return Character.model_validate(payload)


def serialize_session(session: Session) -> dict[str, Any]:
    return session.model_dump(mode="json")


def deserialize_session(data: dict[str, Any]) -> Session:
    return Session.model_validate(data)


def serialize_event(event: WorldEvent) -> dict[str, Any]:
    return event.model_dump(mode="json")


def deserialize_event(data: dict[str, Any]) -> WorldEvent:
    return WorldEvent.model_validate(data)
