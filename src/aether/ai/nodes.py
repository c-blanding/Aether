from __future__ import annotations

import json
from typing import Any

from langchain_core.runnables import RunnableConfig

from aether.ai.context import (
    ActOneContext,
    ActionSchemaBrief,
    ActorContext,
    BeliefBrief,
    CharacterBrief,
    ConnectedLocationBrief,
    GoalBrief,
    LocationBrief,
    MemoryBrief,
    NearbyCharacterBrief,
    PlannerCharacterContext,
    PlannerLocationContext,
    PresentationTone,
    RelationshipBrief,
    ScenePayload,
    VisibleItemBrief,
)
from aether.ai.prompts import (
    DECIDE_SYSTEM,
    DECIDE_USER,
    DIALOGUE_SYSTEM,
    DIALOGUE_USER,
    NARRATIVE_SYSTEM,
    NARRATIVE_USER,
    style_system_suffix,
)
from aether.domain.presentation import PresentationStyle, SceneSummary
from aether.ai.state import (
    GeneratedDialogueLines,
    GeneratedNarrative,
    InteractionState,
    NextStepDecision,
)
from aether.components.planner import ReactivePlanner
from aether.components.shared import AetherValidationError
from aether.domain.actions import Action, WorldAction
from aether.modules.dialogue import SPEAKING_EVENT_TYPES


def _cfg(config: RunnableConfig) -> dict[str, Any]:
    return (config or {}).get("configurable") or {}


def _serialize_event(event: Any) -> dict[str, Any]:
    if hasattr(event, "model_dump"):
        return event.model_dump(mode="json")
    return dict(event)


def _relationship_brief(character: Any, target_id: str) -> RelationshipBrief | None:
    rel = character.relationships.relationships.get(target_id)
    if rel is None:
        return None
    return RelationshipBrief(
        target_character_id=rel.target_character_id,
        trust=rel.trust,
        affinity=rel.affinity,
        fear=rel.fear,
        suspicion=rel.suspicion,
    )


def _build_context(
    world: Any,
    aether: Any,
    actor_id: str,
    message: str,
    scene_summary: SceneSummary | None = None,
) -> ActOneContext:
    actor = world.characters.get(actor_id)
    location_id = actor.state.location_id if actor is not None else None
    location = world.locations.get(location_id) if location_id else None

    nearby_characters: list[PlannerCharacterContext] = []
    for character in world.characters.values():
        if character.state.location_id != location_id:
            continue
        nearby_characters.append(
            PlannerCharacterContext(
                id=character.id,
                name=character.name,
                role=character.identity.role,
                emotion=character.state.emotion,
                goals=[
                    GoalBrief(description=g.description, priority=g.priority)
                    for g in character.goals.prioritize()[:5]
                ],
                beliefs=[
                    b.proposition
                    for b in list(character.knowledge.beliefs.values())[:5]
                ],
                memories=[
                    m.perspective
                    for m in character.recall(
                        message,
                        location_ids=[location_id] if location_id else None,
                        participant_ids=[actor_id] if actor_id else None,
                        limit=5,
                    )
                ],
                personality=character.personality,
                relationship_to_actor=(
                    _relationship_brief(character, actor_id)
                    if actor_id and character.id != actor_id
                    else None
                ),
            )
        )

    nearby_items: list[VisibleItemBrief] = []
    for item in world.items.values():
        if getattr(item, "hidden", False) and item.state.owner_id != (
            actor.id if actor else None
        ):
            continue
        if item.state.location_id == location_id or (
            actor is not None and item.state.owner_id == actor.id
        ):
            nearby_items.append(
                VisibleItemBrief(
                    id=item.id,
                    name=item.name,
                    description=item.description,
                    location_id=item.state.location_id,
                    owner_id=item.state.owner_id,
                )
            )

    connected: list[ConnectedLocationBrief] = []
    if location is not None:
        for dest_id in location.connected_location_ids:
            dest = world.locations.get(dest_id)
            if dest is not None:
                connected.append(
                    ConnectedLocationBrief(id=dest.id, name=dest.name)
                )

    action_schemas = [
        ActionSchemaBrief(
            type=registered.action_type,
            module=registered.module_name,
            required_capability=registered.required_capability,
            parameters_schema=registered.parameter_model.model_json_schema(),
        )
        for registered in aether.engine.modules.actions.list_actions()
    ]

    return ActOneContext(
        actor=ActorContext(
            id=actor_id,
            name=world.describe_character(actor_id),
            location_id=location_id,
            location_name=world.describe_location(location_id),
            inventory=list(actor.inventory.item_ids) if actor else [],
        ),
        location=PlannerLocationContext(
            id=location_id,
            name=location.name if location else None,
            description=location.description if location else None,
            connected_locations=connected,
        ),
        nearby_characters=nearby_characters,
        nearby_items=nearby_items,
        available_actions=action_schemas,
        recent_event_types=[e.type for e in world.events.latest(8)],
        scene_summary=scene_summary or SceneSummary(),
    )


def gather_context(
    state: InteractionState,
    config: RunnableConfig,
) -> InteractionState:
    cfg = _cfg(config)
    session = cfg.get("session")
    summary = (
        session.scene_summary
        if session is not None
        else SceneSummary()
    )
    context = _build_context(
        cfg["world"],
        cfg["aether"],
        state.get("actor_id") or "",
        state.get("message") or "",
        scene_summary=summary,
    )
    return {
        "context": context.model_dump(mode="json"),
        "speaking_pending": False,
        "presentation_pending": False,
        "npc_actions_taken": 0,
        "npc_acted_ids": [],
        "last_executed_actor_id": None,
        "trace_steps": ["gather_context"],
    }


def decide_next_action(
    state: InteractionState,
    config: RunnableConfig,
) -> InteractionState:
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
            "turn_decisions": [
                {
                    "kind": "respond",
                    "reason": "max_steps reached",
                    "source": "planner",
                    "actor_id": state.get("actor_id"),
                }
            ],
            "trace_steps": ["decide_next_action:max_steps"],
        }

    if model is None:
        raise AetherValidationError(
            "decide_next_action requires a language model."
        )

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

    context = state.get("context") or {}
    scene_summary = context.get("scene_summary") or {}
    prompt = DECIDE_USER.format(
        message=state.get("message") or "",
        actor_id=state.get("actor_id") or "",
        scene_summary=json.dumps(scene_summary, indent=2),
        context=json.dumps(context, indent=2),
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
        "turn_decisions": [
            {
                "kind": decision.kind,
                "action_type": decision.action_type,
                "actor_id": state.get("actor_id"),
                "reason": decision.reason,
                "source": "planner",
            }
        ],
        "trace_steps": [
            f"decide_next_action:{decision.kind}"
            + (f":{decision.action_type}" if decision.action_type else "")
        ],
    }


def validate_action(
    state: InteractionState,
    config: RunnableConfig,
) -> InteractionState:
    cfg = _cfg(config)
    aether = cfg["aether"]
    decision = state.get("decision") or {}

    if decision.get("kind") != "action" or not decision.get("action_type"):
        reason = "Decision did not include a valid action."
        return {
            "last_rejection": reason,
            "speaking_pending": False,
            "presentation_pending": False,
            "reject_reasons": [reason],
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
        reason = str(exc)
        return {
            "last_rejection": reason,
            "speaking_pending": False,
            "presentation_pending": False,
            "reject_reasons": [reason],
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
) -> InteractionState:
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
    result = aether.step(world, action, session=cfg.get("session"))
    player_id = state.get("actor_id") or ""

    decision_source = (state.get("decision") or {}).get("source") or "planner"

    if not result.accepted:
        reason = result.reason or "Action rejected."
        return {
            "last_rejection": reason,
            "last_events": [],
            "speaking_pending": False,
            "presentation_pending": False,
            "last_executed_actor_id": action.actor_id,
            "reject_reasons": [reason],
            "turn_decisions": [
                {
                    "kind": "action",
                    "action_type": action.type,
                    "actor_id": action.actor_id,
                    "accepted": False,
                    "rejection": reason,
                    "source": decision_source,
                }
            ],
            "trace_steps": [f"execute_action:reject:{result.reason}"],
        }

    event_dicts = [_serialize_event(event) for event in result.events]
    speaking = any(
        event.data.type in SPEAKING_EVENT_TYPES for event in result.events
    )
    session = cfg.get("session")
    summary = (
        session.scene_summary
        if session is not None
        else SceneSummary()
    )
    refreshed = _build_context(
        world,
        aether,
        player_id,
        state.get("message") or "",
        scene_summary=summary,
    )
    npc_actions_taken = int(state.get("npc_actions_taken") or 0)
    npc_acted_ids = list(state.get("npc_acted_ids") or [])
    if action.actor_id == player_id:
        npc_actions_taken = 0
        npc_acted_ids = []
    elif decision_source == "npc_react":
        npc_actions_taken += 1
        if action.actor_id and action.actor_id not in npc_acted_ids:
            npc_acted_ids.append(action.actor_id)

    relationship_deltas = [
        delta.model_dump(mode="json")
        for delta in (result.relationship_deltas or [])
    ]

    return {
        "last_rejection": None,
        "last_events": event_dicts,
        "events": event_dicts,
        "actions": [action.model_dump(mode="json")],
        "speaking_pending": speaking,
        "presentation_pending": bool(event_dicts),
        "last_executed_actor_id": action.actor_id,
        "npc_actions_taken": npc_actions_taken,
        "npc_acted_ids": npc_acted_ids,
        "context": refreshed.model_dump(mode="json"),
        "perception_count": result.perception_count,
        "memory_count": result.memory_count,
        "beliefs_formed": result.beliefs_formed,
        "relationship_deltas": relationship_deltas,
        "turn_decisions": [
            {
                "kind": "action",
                "action_type": action.type,
                "actor_id": action.actor_id,
                "accepted": True,
                "source": decision_source,
            }
        ],
        "trace_steps": [
            f"execute_action:ok:{action.type}:events={len(event_dicts)}"
            f":actor={action.actor_id}"
        ],
    }


def _collect_character_ids(events: list[dict[str, Any]]) -> set[str]:
    character_ids: set[str] = set()
    for event in events:
        actor_id = event.get("actor_id")
        if actor_id:
            character_ids.add(actor_id)
        attrs = (event.get("data") or {}).get("attributes") or {}
        for key in (
            "speaker_id",
            "listener_id",
            "questioner_id",
            "new_owner_id",
            "character_id",
            "from_character_id",
            "to_character_id",
            "used_by_id",
        ):
            if attrs.get(key):
                character_ids.add(attrs[key])
        for listener_id in attrs.get("listener_ids") or []:
            if isinstance(listener_id, str):
                character_ids.add(listener_id)
        for target_id in attrs.get("target_ids") or []:
            if isinstance(target_id, str) and target_id.startswith("char_"):
                character_ids.add(target_id)
    return character_ids


def _character_briefs(
    world: Any,
    character_ids: set[str],
    recall_query: str,
) -> list[CharacterBrief]:
    briefs: list[CharacterBrief] = []
    for character_id in character_ids:
        character = world.characters.get(character_id)
        if character is None:
            continue
        location = world.locations.get(character.state.location_id or "")
        briefs.append(
            CharacterBrief(
                id=character.id,
                name=character.name,
                role=character.identity.role,
                background=character.identity.background,
                personality=character.personality,
                emotion=character.state.emotion,
                status=character.state.status,
                location=LocationBrief(
                    id=character.state.location_id,
                    name=location.name if location else None,
                    description=location.description if location else None,
                ),
                goals=[
                    GoalBrief(description=g.description, priority=g.priority)
                    for g in character.goals.prioritize()[:6]
                ],
                beliefs=[
                    BeliefBrief(
                        proposition=b.proposition,
                        believed_value=b.believed_value,
                        confidence=b.confidence,
                    )
                    for b in list(character.knowledge.beliefs.values())[:8]
                ],
                memories=[
                    MemoryBrief(
                        perspective=m.perspective,
                        importance=m.importance,
                        emotion=m.emotion,
                    )
                    for m in character.recall(
                        recall_query,
                        location_ids=[character.state.location_id]
                        if character.state.location_id
                        else None,
                        limit=8,
                    )
                ],
                relationships=[
                    RelationshipBrief(
                        target_character_id=rel.target_character_id,
                        trust=rel.trust,
                        affinity=rel.affinity,
                        fear=rel.fear,
                        suspicion=rel.suspicion,
                    )
                    for rel in list(character.relationships.relationships.values())[
                        :8
                    ]
                ],
            )
        )
    return briefs


def _scene_payload(
    world: Any,
    actor_id: str,
    events: list[dict[str, Any]],
    scene_summary: SceneSummary | None = None,
) -> ScenePayload:
    actor = world.characters.get(actor_id)
    location_id = actor.state.location_id if actor is not None else None
    location = world.locations.get(location_id) if location_id else None

    nearby = [
        NearbyCharacterBrief(
            id=character.id,
            name=character.name,
            role=character.identity.role,
            emotion=character.state.emotion,
        )
        for character in world.characters.values()
        if character.state.location_id == location_id
    ]

    visible_items = [
        VisibleItemBrief(
            id=item.id,
            name=item.name,
            description=item.description,
            owner_id=item.state.owner_id,
            location_id=item.state.location_id,
        )
        for item in world.items.values()
        if (
            not getattr(item, "hidden", False)
            or (actor is not None and item.state.owner_id == actor.id)
        )
        and (
            item.state.location_id == location_id
            or (actor is not None and item.state.owner_id == actor.id)
        )
    ]

    return ScenePayload(
        world_name=world.metadata.name if world.metadata else None,
        world_description=world.metadata.description if world.metadata else None,
        location=LocationBrief(
            id=location_id,
            name=location.name if location else None,
            description=location.description if location else None,
        ),
        nearby_characters=nearby,
        visible_items=visible_items,
        event_types=[
            (event.get("data") or {}).get("type") for event in events
        ],
        scene_summary=scene_summary or SceneSummary(),
    )


def _dump_models(models: list[Any]) -> str:
    return json.dumps(
        [model.model_dump(mode="json") for model in models],
        indent=2,
    )


def _render_narrative(
    *,
    model: Any,
    message: str,
    events: list[dict[str, Any]],
    scene: ScenePayload,
    characters: list[CharacterBrief],
    tone: PresentationTone | None = None,
    scene_summary: SceneSummary | None = None,
) -> str:
    tone = tone or PresentationTone()
    summary = scene_summary or scene.scene_summary
    prompt = NARRATIVE_USER.format(
        message=message or "",
        scene_summary=summary.model_dump_json(indent=2),
        events=json.dumps(events, indent=2),
        scene=scene.model_dump_json(indent=2),
        characters=_dump_models(characters),
        tone=tone.model_dump_json(indent=2),
    )
    system = NARRATIVE_SYSTEM + style_system_suffix(tone.style)
    structured = model.with_structured_output(
        GeneratedNarrative,
        method="function_calling",
    )
    generated: GeneratedNarrative = structured.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
    )
    return (generated.narrative or "").strip()


def _render_dialogue(
    *,
    model: Any,
    message: str,
    speaking_events: list[dict[str, Any]],
    scene: ScenePayload,
    characters: list[CharacterBrief],
    narrative: str,
    style: PresentationStyle | None = None,
    scene_summary: SceneSummary | None = None,
) -> list[dict[str, Any]]:
    style = style or PresentationStyle()
    summary = scene_summary or scene.scene_summary
    prompt = DIALOGUE_USER.format(
        message=message or "",
        scene_summary=summary.model_dump_json(indent=2),
        events=json.dumps(speaking_events, indent=2),
        scene=scene.model_dump_json(indent=2),
        characters=_dump_models(characters),
        style=style.model_dump_json(indent=2),
        narrative=narrative or "(none)",
    )
    system = DIALOGUE_SYSTEM + style_system_suffix(style)
    structured = model.with_structured_output(
        GeneratedDialogueLines,
        method="function_calling",
    )
    generated: GeneratedDialogueLines = structured.invoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
    )
    return [line.model_dump(mode="json") for line in generated.lines]


def generate_dialogue(
    state: InteractionState,
    config: RunnableConfig,
) -> InteractionState:
    """
    Host presentation pass: narrative renderer always; dialogue renderer when speaking.
    """
    cfg = _cfg(config)
    world = cfg["world"]
    model = cfg.get("model")
    last_events = state.get("last_events") or []
    message = state.get("message") or ""

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
        raise AetherValidationError(
            "generate_dialogue requires a language model."
        )

    recall_query = " ".join(
        filter(
            None,
            [
                message,
                *[
                    (e.get("data") or {}).get("attributes", {}).get("topic", "")
                    for e in last_events
                ],
            ],
        )
    )
    character_ids = _collect_character_ids(last_events)
    # Include nearby people for richer staging / possible interjections.
    actor = world.characters.get(state.get("actor_id") or "")
    location_id = actor.state.location_id if actor is not None else None
    for character in world.characters.values():
        if character.state.location_id == location_id:
            character_ids.add(character.id)

    briefs = _character_briefs(world, character_ids, recall_query)
    session = cfg.get("session")
    summary = (
        session.scene_summary
        if session is not None
        else SceneSummary()
    )
    style = cfg.get("style") or PresentationStyle()
    if isinstance(style, dict):
        style = PresentationStyle.model_validate(style)
    scene = _scene_payload(
        world,
        state.get("actor_id") or "",
        last_events,
        scene_summary=summary,
    )
    tone = PresentationTone(
        generation_mode="narrative_then_dialogue",
        has_speaking_events=bool(speaking_events),
        style=style,
    )

    narrative = _render_narrative(
        model=model,
        message=message,
        events=last_events,
        scene=scene,
        characters=briefs,
        tone=tone,
        scene_summary=summary,
    )

    lines: list[dict[str, Any]] = []
    if speaking_events:
        dialogue_ids = _collect_character_ids(speaking_events)
        dialogue_briefs = [
            brief for brief in briefs if brief.id in dialogue_ids
        ] or briefs
        lines = _render_dialogue(
            model=model,
            message=message,
            speaking_events=speaking_events,
            scene=scene,
            characters=dialogue_briefs,
            narrative=narrative,
            style=style,
            scene_summary=summary,
        )

    return {
        "dialogue": lines,
        "narrative_parts": [narrative] if narrative else [],
        "speaking_pending": False,
        "presentation_pending": False,
        "trace_steps": [
            "generate_dialogue:"
            f"narrative={bool(narrative)}:lines={len(lines)}"
        ],
    }


def npc_react(
    state: InteractionState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """
    Optional reactive NPC beat(s) after presentation.

    Allows up to ``max_npc_actions`` reactions per player message. After each
    accepted NPC action the graph re-presents and returns here with refreshed
    context from ``execute_action``.
    """
    cfg = _cfg(config)
    world = cfg["world"]
    aether = cfg["aether"]
    player_id = state.get("actor_id") or ""
    last_actor = state.get("last_executed_actor_id")
    taken = int(state.get("npc_actions_taken") or 0)
    if state.get("max_npc_actions") is not None:
        max_npc = int(state.get("max_npc_actions"))
    elif cfg.get("max_npc_actions") is not None:
        max_npc = int(cfg.get("max_npc_actions"))
    else:
        max_npc = 2
    acted_ids = set(state.get("npc_acted_ids") or [])

    # First reaction must follow a player beat; later ones may follow NPC beats.
    if taken == 0 and (not last_actor or last_actor != player_id):
        return {
            "decision": {"kind": "continue"},
            "trace_steps": ["npc_react:skip"],
        }
    if taken >= max_npc:
        return {
            "decision": {"kind": "continue"},
            "trace_steps": [f"npc_react:cap:{taken}"],
        }

    recent_events = state.get("last_events") or []
    if not recent_events:
        return {
            "decision": {"kind": "continue"},
            "trace_steps": ["npc_react:no_events"],
        }

    available = set(aether.engine.list_action_types())
    reaction = ReactivePlanner().propose(
        world,
        player_id=player_id,
        recent_events=recent_events,
        available_action_types=available,
        exclude_character_ids=acted_ids,
    )
    if reaction is None:
        return {
            "decision": {"kind": "continue"},
            "trace_steps": ["npc_react:none"],
        }

    try:
        validated = aether.engine.modules.actions.validate(reaction.action)
    except Exception as exc:  # noqa: BLE001
        return {
            "decision": {"kind": "continue"},
            "trace_steps": [f"npc_react:invalid:{exc}"],
        }

    return {
        "decision": {
            "kind": "action",
            "action_type": validated.type,
            "parameters": validated.data.parameters,
            "target_id": validated.target_id,
            "reason": reaction.reason,
            "validated_action": validated.model_dump(mode="json"),
            "source": "npc_react",
        },
        "last_rejection": None,
        "turn_decisions": [
            {
                "kind": "action",
                "action_type": validated.type,
                "actor_id": validated.actor_id,
                "reason": reaction.reason,
                "source": "npc_react",
            }
        ],
        "trace_steps": [
            f"npc_react:action:{validated.type}:{validated.actor_id}"
            f":{taken + 1}/{max_npc}"
        ],
    }
