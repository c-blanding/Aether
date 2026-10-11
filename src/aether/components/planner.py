from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from aether.domain.actions import Action, WorldAction

_WITHDRAW_TOKENS = (
    "withdraw",
    "leave",
    "escape",
    "flee",
    "avoid",
    "hide",
    "retreat",
    "get away",
)
_PROTECT_TOKENS = (
    "protect",
    "secret",
    "hide",
    "reputation",
    "guard",
    "conceal",
)
_CONFRONT_TOKENS = (
    "confront",
    "accuse",
    "challenge",
    "question",
    "interrogate",
    "expose",
)


@dataclass
class NpcReaction:
    """A proposed NPC reaction from the reactive planner."""

    action: Action
    reason: str
    importance: float


class Planner:
    """
    Planning configuration for character behavior.
    """

    def __init__(self, strategy: str = "goal_driven") -> None:
        self.strategy = strategy


class ReactivePlanner:
    """
    Post-player-beat NPC policy (v2).

    Scores candidates by recent high-importance memory **and** active goals,
    then proposes speak / say_to / ask_question / move. Hosts may request up to
    a few reactions per player message; callers re-gather world state between
    accepted actions.
    """

    def __init__(
        self,
        importance_threshold: float = 0.6,
        min_score: float = 0.65,
    ) -> None:
        self.importance_threshold = importance_threshold
        self.min_score = min_score

    def propose(
        self,
        world: Any,
        *,
        player_id: str,
        recent_events: list[Any],
        available_action_types: set[str],
        exclude_character_ids: Optional[set[str]] = None,
    ) -> Optional[NpcReaction]:
        if not recent_events:
            return None

        event_ids = {
            event.id if hasattr(event, "id") else event.get("id")
            for event in recent_events
        }
        event_ids.discard(None)
        excluded = exclude_character_ids or set()

        candidates: list[tuple[float, Any, list[Any], str]] = []
        for character in world.characters.values():
            if character.id == player_id or character.id in excluded:
                continue
            if character.state.status != "active":
                continue

            triggered = self._triggered_memories(character, event_ids)
            if not triggered:
                continue

            best = max(triggered, key=lambda m: m.importance)
            score, intent = self._score_candidate(character, best)
            if score < self.min_score:
                continue
            candidates.append((score, character, triggered, intent))

        if not candidates:
            return None

        candidates.sort(key=lambda row: row[0], reverse=True)
        score, npc, memories, intent = candidates[0]
        top_memory = max(memories, key=lambda m: m.importance)
        return self._build_reaction(
            world,
            npc=npc,
            player_id=player_id,
            memory=top_memory,
            score=score,
            intent=intent,
            available_action_types=available_action_types,
        )

    def _triggered_memories(self, character: Any, event_ids: set[Any]) -> list[Any]:
        triggered = []
        episodic = character.memory.episodic[-12:]
        for memory in episodic:
            if memory.importance < self.importance_threshold:
                continue
            if event_ids and not set(memory.source_event_ids) & event_ids:
                if memory not in character.memory.episodic[-3:]:
                    continue
            triggered.append(memory)
        return triggered

    def _score_candidate(
        self,
        character: Any,
        memory: Any,
    ) -> tuple[float, str]:
        score = float(memory.importance)
        if memory.emotion:
            score += 0.15

        intent = "engage"
        goals = character.goals.prioritize()[:5]
        for goal in goals:
            text = goal.description.lower()
            weight = goal.priority / 400.0
            if any(token in text for token in _WITHDRAW_TOKENS):
                score += weight + 0.08
                intent = "withdraw"
            elif any(token in text for token in _PROTECT_TOKENS):
                score += weight
                if intent != "withdraw":
                    intent = "protect"
            elif any(token in text for token in _CONFRONT_TOKENS):
                score += weight + 0.05
                if intent == "engage":
                    intent = "confront"

        # Relationship pressure toward recent participants.
        for participant_id in getattr(memory, "participant_ids", []) or []:
            if participant_id == character.id:
                continue
            rel = character.relationships.relationships.get(participant_id)
            if rel is None:
                continue
            if rel.suspicion >= 0.3 or rel.fear >= 0.3:
                score += 0.08
                if intent == "engage":
                    intent = "confront"
            if rel.affinity >= 0.4:
                score += 0.04

        return score, intent

    def _build_reaction(
        self,
        world: Any,
        *,
        npc: Any,
        player_id: str,
        memory: Any,
        score: float,
        intent: str,
        available_action_types: set[str],
    ) -> Optional[NpcReaction]:
        player = world.characters.get(player_id)
        same_room = (
            player is not None
            and player.state.location_id is not None
            and player.state.location_id == npc.state.location_id
        )
        topic = (memory.perspective or memory.summary or "what just happened")[:120]

        if intent == "withdraw" and "move" in available_action_types:
            move = self._leave_action(world, npc=npc, topic=topic, score=score)
            if move is not None:
                return move

        if same_room and intent == "confront" and "ask_question" in available_action_types:
            return NpcReaction(
                action=Action(
                    actor_id=npc.id,
                    target_id=player_id,
                    data=WorldAction(
                        type="ask_question",
                        module="dialogue",
                        parameters={
                            "target_character_ids": [player_id],
                            "topic": topic,
                        },
                    ),
                ),
                reason=f"{npc.name} presses about: {topic}",
                importance=score,
            )

        if same_room and "say_to" in available_action_types:
            return NpcReaction(
                action=Action(
                    actor_id=npc.id,
                    target_id=player_id,
                    data=WorldAction(
                        type="say_to",
                        module="dialogue",
                        parameters={
                            "target_character_id": player_id,
                            "topic": topic,
                        },
                    ),
                ),
                reason=f"{npc.name} reacts to: {topic}",
                importance=score,
            )

        if same_room and "speak" in available_action_types:
            return NpcReaction(
                action=Action(
                    actor_id=npc.id,
                    data=WorldAction(
                        type="speak",
                        module="dialogue",
                        parameters={"topic": topic},
                    ),
                ),
                reason=f"{npc.name} speaks about: {topic}",
                importance=score,
            )

        if "move" in available_action_types and (
            intent in {"withdraw", "protect"} or not same_room
        ):
            return self._leave_action(world, npc=npc, topic=topic, score=score)

        return None

    def _leave_action(
        self,
        world: Any,
        *,
        npc: Any,
        topic: str,
        score: float,
    ) -> Optional[NpcReaction]:
        if not npc.state.location_id:
            return None
        location = world.locations.get(npc.state.location_id)
        if not location or not location.connected_location_ids:
            return None
        destination = location.connected_location_ids[0]
        return NpcReaction(
            action=Action(
                actor_id=npc.id,
                data=WorldAction(
                    type="move",
                    module="navigation",
                    parameters={
                        "destination_location_id": destination,
                    },
                ),
            ),
            reason=f"{npc.name} leaves after: {topic}",
            importance=score,
        )
