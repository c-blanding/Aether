from __future__ import annotations

from typing import Iterable, List, Optional

from aether.domain.events import WorldEvent
from aether.domain.relationship import RelationshipDelta
from aether.domain.world import World
from aether.engine.registries import ModuleRegistry
from aether.modules.base import AetherModule

# Topic tokens that tilt a social beat toward warmth vs conflict.
_WARM_TOKENS = (
    "thank",
    "sorry",
    "please",
    "friend",
    "trust",
    "help",
    "care",
    "glad",
    "welcome",
    "appreciate",
    "greet",
    "hello",
    "hi ",
)
_COLD_TOKENS = (
    "lie",
    "threat",
    "accuse",
    "suspect",
    "guilty",
    "murder",
    "steal",
    "betray",
    "hate",
    "fool",
    "idiot",
    "damn",
    "evidence",
    "caught",
    "secret",
)


class SocialModule(AetherModule):
    """
    Thin social outcomes layer.

    Does not register player verbs. After dialogue / detective social events
    commit, applies small directional relationship deltas so trust, affinity,
    fear, and suspicion evolve during play.
    """

    name = "social"
    version = "0.1.0"

    def register(self, registry: ModuleRegistry) -> None:
        # Outcomes-only module; actions/events live in dialogue / detective.
        return None

    def apply_outcomes(
        self,
        world: World,
        events: Iterable[WorldEvent],
    ) -> List[RelationshipDelta]:
        deltas: list[RelationshipDelta] = []
        for event in events:
            event_type = event.type
            if event_type == "dialogue_spoken":
                deltas.extend(self._from_dialogue_spoken(world, event))
            elif event_type == "question_asked":
                deltas.extend(self._from_question_asked(world, event))
            elif event_type == "question_answered":
                deltas.extend(self._from_question_answered(world, event))
            elif event_type == "evidence_presented":
                deltas.extend(self._from_evidence_presented(world, event))
        return deltas

    def _topic_bias(self, topic: str) -> str:
        lowered = (topic or "").lower()
        if any(token in lowered for token in _COLD_TOKENS):
            return "cold"
        if any(token in lowered for token in _WARM_TOKENS):
            return "warm"
        return "neutral"

    def _apply(
        self,
        world: World,
        *,
        from_id: str,
        to_id: str,
        trust: float = 0.0,
        affinity: float = 0.0,
        fear: float = 0.0,
        suspicion: float = 0.0,
        reason: str,
        event_id: Optional[str],
    ) -> Optional[RelationshipDelta]:
        if from_id == to_id:
            return None
        character = world.characters.get(from_id)
        if character is None or to_id not in world.characters:
            return None
        if trust == affinity == fear == suspicion == 0.0:
            return None

        character.update_relationship(
            to_id,
            trust_delta=trust,
            affinity_delta=affinity,
            fear_delta=fear,
            suspicion_delta=suspicion,
        )
        return RelationshipDelta(
            from_character_id=from_id,
            to_character_id=to_id,
            trust_delta=trust,
            affinity_delta=affinity,
            fear_delta=fear,
            suspicion_delta=suspicion,
            reason=reason,
            event_id=event_id,
        )

    def _from_dialogue_spoken(
        self,
        world: World,
        event: WorldEvent,
    ) -> list[RelationshipDelta]:
        attrs = event.data.attributes or {}
        speaker_id = attrs.get("speaker_id") or event.actor_id
        listener_id = attrs.get("listener_id")
        topic = str(attrs.get("topic") or "")
        bias = self._topic_bias(topic)
        deltas: list[RelationshipDelta] = []

        if not speaker_id or not listener_id:
            return deltas

        if bias == "warm":
            pair = (
                (listener_id, speaker_id, 0.05, 0.08, 0.0, -0.03, "warm address"),
                (speaker_id, listener_id, 0.02, 0.04, 0.0, 0.0, "warm address"),
            )
        elif bias == "cold":
            pair = (
                (
                    listener_id,
                    speaker_id,
                    -0.06,
                    -0.05,
                    0.04,
                    0.08,
                    "hostile address",
                ),
                (speaker_id, listener_id, -0.02, -0.03, 0.0, 0.02, "hostile address"),
            )
        else:
            pair = (
                (listener_id, speaker_id, 0.01, 0.02, 0.0, 0.0, "direct address"),
                (speaker_id, listener_id, 0.0, 0.01, 0.0, 0.0, "direct address"),
            )

        for from_id, to_id, trust, affinity, fear, suspicion, reason in pair:
            delta = self._apply(
                world,
                from_id=from_id,
                to_id=to_id,
                trust=trust,
                affinity=affinity,
                fear=fear,
                suspicion=suspicion,
                reason=reason,
                event_id=event.id,
            )
            if delta is not None:
                deltas.append(delta)
        return deltas

    def _from_question_asked(
        self,
        world: World,
        event: WorldEvent,
    ) -> list[RelationshipDelta]:
        attrs = event.data.attributes or {}
        speaker_id = attrs.get("speaker_id") or event.actor_id
        listener_ids = list(attrs.get("listener_ids") or [])
        topic = str(attrs.get("topic") or "")
        bias = self._topic_bias(topic)
        deltas: list[RelationshipDelta] = []
        if not speaker_id:
            return deltas

        suspicion = 0.06 if bias == "cold" else 0.03
        fear = 0.03 if bias == "cold" else 0.0
        affinity = -0.02 if bias == "cold" else 0.0

        for listener_id in listener_ids:
            delta = self._apply(
                world,
                from_id=listener_id,
                to_id=speaker_id,
                trust=-0.02 if bias == "cold" else 0.0,
                affinity=affinity,
                fear=fear,
                suspicion=suspicion,
                reason="question asked",
                event_id=event.id,
            )
            if delta is not None:
                deltas.append(delta)
        return deltas

    def _from_question_answered(
        self,
        world: World,
        event: WorldEvent,
    ) -> list[RelationshipDelta]:
        attrs = event.data.attributes or {}
        speaker_id = attrs.get("speaker_id") or event.actor_id
        questioner_id = attrs.get("questioner_id")
        topic = str(attrs.get("topic") or "")
        bias = self._topic_bias(topic)
        deltas: list[RelationshipDelta] = []
        if not speaker_id or not questioner_id:
            return deltas

        if bias == "cold":
            trust, affinity, suspicion = -0.03, -0.02, 0.04
            reason = "evasive or tense answer"
        elif bias == "warm":
            trust, affinity, suspicion = 0.05, 0.04, -0.02
            reason = "cooperative answer"
        else:
            trust, affinity, suspicion = 0.03, 0.02, -0.01
            reason = "answered question"

        delta = self._apply(
            world,
            from_id=questioner_id,
            to_id=speaker_id,
            trust=trust,
            affinity=affinity,
            suspicion=suspicion,
            reason=reason,
            event_id=event.id,
        )
        if delta is not None:
            deltas.append(delta)
        return deltas

    def _from_evidence_presented(
        self,
        world: World,
        event: WorldEvent,
    ) -> list[RelationshipDelta]:
        attrs = event.data.attributes or {}
        actor_id = attrs.get("actor_id") or event.actor_id
        target_id = attrs.get("target_character_id")
        deltas: list[RelationshipDelta] = []
        if not actor_id or not target_id:
            return deltas

        # Target grows suspicion/fear toward presenter; presenter trusts less.
        for from_id, to_id, trust, affinity, fear, suspicion, reason in (
            (
                target_id,
                actor_id,
                -0.08,
                -0.05,
                0.1,
                0.15,
                "damning evidence presented",
            ),
            (
                actor_id,
                target_id,
                -0.04,
                -0.03,
                0.0,
                0.08,
                "presented evidence",
            ),
        ):
            delta = self._apply(
                world,
                from_id=from_id,
                to_id=to_id,
                trust=trust,
                affinity=affinity,
                fear=fear,
                suspicion=suspicion,
                reason=reason,
                event_id=event.id,
            )
            if delta is not None:
                deltas.append(delta)
        return deltas
