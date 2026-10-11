from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from aether.ai.prompts import (
    DECIDE_SYSTEM,
    DECIDE_USER,
    PRESENTATION_SYSTEM,
    PRESENTATION_USER,
)
from aether.ai.state import (
    GeneratedPresentation,
    InteractionState,
    NextStepDecision,
)
from aether.domain.actions import Action, WorldAction
from aether.modules.dialogue import SPEAKING_EVENT_TYPES


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return (config or {}).get("configurable") or {}


def _serialize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    return dict(event)


def _build_context(
    world: Any,
    aether: Any,
    actor_id: str,
    message: str,
) -> dict[str, Any]:
    actor = world.characters.get(actor_id)
    location_id = actor.state.location_id if actor is not None else None
    location = world.locations.get(location_id) if location_id else None

    nearby_characters = []
    for character in world.characters.values():
        if character.state.location_id != location_id:
            continue
        nearby_characters.append(
            {
                "id": character.id,
                "name": character.name,
                "role": character.identity.role,
                "emotion": character.state.emotion,
                "goals": [
                    {"description": g.description, "priority": g.priority}
                    for g in character.goals.prioritize()[:5]
                ],
                "beliefs": [
                    b.proposition
                    for b in list(character.knowledge.beliefs.values())[:5]
                ],
                "memories": [
                    m.perspective for m in character.recall(message)[:5]
                ],
                "personality": character.personality.model_dump(mode="json"),
            }
        )

    nearby_items = []
    for item in world.items.values():
        if item.state.location_id == location_id or (
            actor is not None and item.state.owner_id == actor.id
        ):
            nearby_items.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "location_id": item.state.location_id,
                    "owner_id": item.state.owner_id,
                }
            )

    connected = []
    if location is not None:
        for dest_id in location.connected_location_ids:
            dest = world.locations.get(dest_id)
            if dest is not None:
                connected.append({"id": dest.id, "name": dest.name})

    action_schemas = []
    for registered in aether.engine.modules.actions.list_actions():
        action_schemas.append(
            {
                "type": registered.action_type,
                "module": registered.module_name,
                "parameters_schema": registered.parameter_model.model_json_schema(),
            }
        )

    return {
        "actor": {
            "id": actor_id,
            "name": world.describe_character(actor_id),
            "location_id": location_id,
            "location_name": world.describe_location(location_id),
            "inventory": list(actor.inventory.item_ids) if actor else [],
        },
        "location": {
            "id": location_id,
            "name": location.name if location else None,
            "description": location.description if location else None,
            "connected_locations": connected,
        },
        "nearby_characters": nearby_characters,
        "nearby_items": nearby_items,
        "available_actions": action_schemas,
        "recent_event_types": [e.type for e in world.events.latest(8)],
    }


def gather_context(
    state: InteractionState,
    config: RunnableConfig,
) -> dict[str, Any]:
    cfg = _cfg(config)
    context = _build_context(
        cfg["world"],
        cfg["aether"],
        state.get("actor_id") or "",
        state.get("message") or "",
    )
    return {
        "context": context,
        "speaking_pending": False,
        "presentation_pending": False,
        "trace_steps": ["gather_context"],
    }


def decide_next_action(
    state: InteractionState,
    config: RunnableConfig,
) -> dict[str, Any]:
    cfg = _cfg(config)
    model = cfg.get("model")
    step_count = int(state.get("step_count") or 0) + 1
    max_steps = int(state.get("max_steps") or 6)

    if step_count > max_steps:
        return {
            "decision": {"kind": "respond", "reason": "max_steps reached"},
            "done": True,
            "status": "completed",
            "step_count": step_count,
            "trace_steps": ["decide_next_action:max_steps"],
        }

    if model is None:
        return {
            "decision": {
                "kind": "respond",
                "reason": "no language model configured",
            },
            "done": True,
            "status": "completed",
            "step_count": step_count,
            "trace_steps": ["decide_next_action:no_model"],
        }

    actions_taken = [
        {
            "type": (action.get("data") or {}).get("type"),
            "parameters": (action.get("data") or {}).get("parameters"),
        }
        for action in (state.get("actions") or [])
    ]
    events_taken = [
        (event.get("data") or {}).get("type")
        for event in (state.get("events") or [])
    ]

    prompt = DECIDE_USER.format(
        message=state.get("message") or "",
        actor_id=state.get("actor_id") or "",
        context=json.dumps(state.get("context") or {}, indent=2),
        actions_taken=json.dumps(actions_taken, indent=2),
        events_taken=json.dumps(events_taken),
        rejection=state.get("last_rejection") or "(none)",
        step_count=step_count,
        max_steps=max_steps,
    )

    structured = model.with_structured_output(
        NextStepDecision,
        method="function_calling",
    )
    decision: NextStepDecision = structured.invoke(
        [
            {"role": "system", "content": DECIDE_SYSTEM},
            {"role": "user", "content": prompt},
        ]
    )

    done = decision.kind == "respond"
    return {
        "decision": decision.model_dump(mode="json"),
        "done": done,
        "status": "completed" if done else state.get("status") or "running",
        "last_rejection": None if done else state.get("last_rejection"),
        "speaking_pending": False,
        "presentation_pending": False,
        "step_count": step_count,
        "trace_steps": [
            f"decide_next_action:{decision.kind}"
            + (f":{decision.action_type}" if decision.action_type else "")
        ],
    }


def validate_action(
    state: InteractionState,
    config: RunnableConfig,
) -> dict[str, Any]:
    cfg = _cfg(config)
    aether = cfg["aether"]
    decision = state.get("decision") or {}

    if decision.get("kind") != "action" or not decision.get("action_type"):
        return {
            "last_rejection": "Decision did not include a valid action.",
            "speaking_pending": False,
            "presentation_pending": False,
            "trace_steps": ["validate_action:missing_action"],
        }

    action = Action(
        actor_id=state.get("actor_id") or "",
        target_id=decision.get("target_id"),
        data=WorldAction(
            type=decision["action_type"],
            parameters=decision.get("parameters") or {},
        ),
    )

    try:
        validated = aether.engine.modules.actions.validate(action)
    except Exception as exc:  # noqa: BLE001 — surface as rejection feedback
        return {
            "last_rejection": str(exc),
            "speaking_pending": False,
            "presentation_pending": False,
            "trace_steps": [f"validate_action:reject:{exc}"],
        }

    return {
        "decision": {
            **decision,
            "validated_action": validated.model_dump(mode="json"),
        },
        "last_rejection": None,
        "speaking_pending": False,
        "presentation_pending": False,
        "trace_steps": [f"validate_action:ok:{validated.type}"],
    }


def execute_action(
    state: InteractionState,
    config: RunnableConfig,
) -> dict[str, Any]:
    cfg = _cfg(config)
    aether = cfg["aether"]
    world = cfg["world"]
    decision = state.get("decision") or {}
    raw = decision.get("validated_action")
    if not raw:
        return {
            "last_rejection": "No validated action to execute.",
            "speaking_pending": False,
            "presentation_pending": False,
            "trace_steps": ["execute_action:missing"],
        }

    action = Action.model_validate(raw)
    result = aether.step(world, action)

    if not result.accepted:
        return {
            "last_rejection": result.reason or "Action rejected.",
            "last_events": [],
            "speaking_pending": False,
            "presentation_pending": False,
            "trace_steps": [f"execute_action:reject:{result.reason}"],
        }

    event_dicts = [_serialize_event(event) for event in result.events]
    speaking = any(
        event.data.type in SPEAKING_EVENT_TYPES for event in result.events
    )
    refreshed = _build_context(
        world,
        aether,
        state.get("actor_id") or "",
        state.get("message") or "",
    )

    return {
        "last_rejection": None,
        "last_events": event_dicts,
        "events": event_dicts,
        "actions": [action.model_dump(mode="json")],
        "speaking_pending": speaking,
        "presentation_pending": bool(event_dicts),
        "context": refreshed,
        "trace_steps": [
            f"execute_action:ok:{action.type}:events={len(event_dicts)}"
        ],
    }


def _stub_narrative(world: Any, events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for event in events:
        data = event.get("data") or {}
        event_type = data.get("type") or "event"
        attrs = data.get("attributes") or {}
        actor_id = event.get("actor_id")
        actor_name = world.describe_character(actor_id)
        if event_type == "item_picked_up":
            item = world.describe_item(attrs.get("item_id"))
            parts.append(f"{actor_name} picks up the {item}.")
        elif event_type == "character_moved":
            dest = world.describe_location(attrs.get("new_location_id"))
            parts.append(f"{actor_name} moves to the {dest}.")
        elif event_type in SPEAKING_EVENT_TYPES:
            topic = attrs.get("topic") or "something"
            parts.append(f"{actor_name} speaks about {topic}.")
        else:
            parts.append(f"{actor_name} causes {event_type.replace('_', ' ')}.")
    return " ".join(parts).strip() or "Something happens."


def generate_dialogue(
    state: InteractionState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Generate host presentation: narrative always, dialogue when speaking events exist.
    """
    cfg = _cfg(config)
    world = cfg["world"]
    model = cfg.get("model")
    last_events = state.get("last_events") or []

    if not last_events:
        return {
            "speaking_pending": False,
            "presentation_pending": False,
            "trace_steps": ["generate_dialogue:skip"],
        }

    speaking_events = [
        event
        for event in last_events
        if (event.get("data") or {}).get("type") in SPEAKING_EVENT_TYPES
    ]

    if model is None:
        stub_lines = []
        for event in speaking_events:
            attrs = (event.get("data") or {}).get("attributes") or {}
            speaker_id = attrs.get("speaker_id") or event.get("actor_id")
            topic = attrs.get("topic") or "something"
            stub_lines.append(
                {
                    "character_id": speaker_id,
                    "character_name": world.describe_character(speaker_id),
                    "text": f"({topic})",
                    "emotion": None,
                }
            )
        narrative = _stub_narrative(world, last_events)
        return {
            "dialogue": stub_lines,
            "narrative_parts": [narrative] if narrative else [],
            "speaking_pending": False,
            "presentation_pending": False,
            "trace_steps": ["generate_dialogue:stub"],
        }

    character_ids: set[str] = set()
    for event in last_events:
        actor_id = event.get("actor_id")
        if actor_id:
            character_ids.add(actor_id)
        attrs = (event.get("data") or {}).get("attributes") or {}
        for key in ("speaker_id", "listener_id", "new_owner_id", "character_id"):
            if attrs.get(key):
                character_ids.add(attrs[key])

    topic_bits = " ".join(
        (e.get("data") or {}).get("attributes", {}).get("topic", "")
        for e in last_events
    )
    briefs = []
    for character_id in character_ids:
        character = world.characters.get(character_id)
        if character is None:
            continue
        briefs.append(
            {
                "id": character.id,
                "name": character.name,
                "role": character.identity.role,
                "background": character.identity.background,
                "personality": character.personality.model_dump(mode="json"),
                "emotion": character.state.emotion,
                "goals": [g.description for g in character.goals.prioritize()[:5]],
                "beliefs": [
                    b.proposition
                    for b in list(character.knowledge.beliefs.values())[:5]
                ],
                "memories": [
                    m.perspective for m in character.recall(topic_bits or state.get("message") or "")[:6]
                ],
            }
        )

    actor = world.characters.get(state.get("actor_id") or "")
    location_id = actor.state.location_id if actor is not None else None
    scene = {
        "location_id": location_id,
        "location_name": world.describe_location(location_id),
        "world_name": world.metadata.name if world.metadata else None,
        "world_description": world.metadata.description if world.metadata else None,
    }

    prompt = PRESENTATION_USER.format(
        events=json.dumps(last_events, indent=2),
        characters=json.dumps(briefs, indent=2),
        scene=json.dumps(scene, indent=2),
    )
    structured = model.with_structured_output(
        GeneratedPresentation,
        method="function_calling",
    )
    generated: GeneratedPresentation = structured.invoke(
        [
            {"role": "system", "content": PRESENTATION_SYSTEM},
            {"role": "user", "content": prompt},
        ]
    )

    lines = [line.model_dump(mode="json") for line in generated.lines]
    # Drop dialogue if there were no speaking events (model over-generation).
    if not speaking_events:
        lines = []
    narrative = (generated.narrative or "").strip()
    return {
        "dialogue": lines,
        "narrative_parts": [narrative] if narrative else [],
        "speaking_pending": False,
        "presentation_pending": False,
        "trace_steps": [
            f"generate_dialogue:narrative={bool(narrative)}:lines={len(lines)}"
        ],
    }
