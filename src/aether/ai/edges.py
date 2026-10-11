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
) -> Literal["generate_dialogue", "decide_next_action"]:
    if state.get("last_rejection"):
        return "decide_next_action"
    # Any committed events get presentation (narrative + optional dialogue).
    if state.get("presentation_pending") or state.get("last_events"):
        return "generate_dialogue"
    return "decide_next_action"
