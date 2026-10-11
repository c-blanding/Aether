from __future__ import annotations

from typing import Literal

from aether.ai.state import InteractionState


def after_decide(
    state: InteractionState,
) -> Literal["validate_action", "__end__"]:
    if state.get("done") or (state.get("decision") or {}).get("kind") == "respond":
        return "__end__"
    return "validate_action"


def after_validate(
    state: InteractionState,
) -> Literal["execute_action", "decide_next_action"]:
    if state.get("last_rejection"):
        return "decide_next_action"
    decision = state.get("decision") or {}
    if decision.get("validated_action"):
        return "execute_action"
    return "decide_next_action"


def after_execute(
    state: InteractionState,
) -> Literal["generate_dialogue", "npc_react", "decide_next_action"]:
    if state.get("last_rejection"):
        return "decide_next_action"
    if state.get("presentation_pending") or state.get("last_events"):
        return "generate_dialogue"
    return "npc_react"


def after_presentation(
    state: InteractionState,
) -> Literal["npc_react"]:
    return "npc_react"


def after_npc_react(
    state: InteractionState,
) -> Literal["execute_action", "decide_next_action"]:
    decision = state.get("decision") or {}
    if (
        decision.get("source") == "npc_react"
        and decision.get("validated_action")
        and decision.get("kind") == "action"
    ):
        return "execute_action"
    return "decide_next_action"
