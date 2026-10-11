from __future__ import annotations

from typing import TYPE_CHECKING, Any, NoReturn

from aether.components.shared import AetherValidationError
from aether.domain.actions import Action
from aether.domain.events import WorldEvent
from aether.domain.interactions import (
    DialogueLine,
    Interaction,
    InteractionResult,
    InteractionStatus,
    TurnDecision,
    TurnReport,
    unanswered_questions,
)
from aether.domain.presentation import InteractOptions, PresentationStyle
from aether.domain.relationship import RelationshipDelta
from aether.modules.dialogue import SPEAKING_EVENT_TYPES
from aether.domain.sessions import Session
from aether.engine.runtime_engine import RuntimeEngine

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_core.language_models import BaseChatModel

    from aether.aether import Aether
    from aether.domain.world import World


def _raise_missing_ai_extra(exc: ImportError) -> NoReturn:
    raise AetherValidationError(
        "AI features require the optional dependency set. "
        'Install with: pip install "aether-sim[ai]"'
    ) from exc


class AetherAI:
    def __init__(
        self,
        engine: RuntimeEngine,
        model: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
        image_model=None,
        voice_model=None,
    ):
        self.engine = engine
        self.model = model
        self.embeddings = embeddings
        self.image_model = image_model
        self.voice_model = voice_model
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            try:
                from aether.ai.graph import get_interact_graph
            except ImportError as exc:
                _raise_missing_ai_extra(exc)
            self._graph = get_interact_graph()
        return self._graph



    def interact(
        self,
        aether: Aether,
        world: World,
        session: Session,
        interaction: Interaction,
        *,
        max_steps: int = 6,
        options: InteractOptions | None = None,
        style: PresentationStyle | None = None,
        max_npc_actions: int | None = None,
        callbacks: Any = None,
    ) -> InteractionResult:
        """
        Run the act-one LangGraph loop for one player message.
        """
        if self.model is None:
            raise AetherValidationError(
                "AetherAI.interact requires a language model."
            )

        base = (options or InteractOptions()).model_dump()
        if options is None:
            base["max_steps"] = max_steps
        if style is not None:
            base["style"] = style
        if max_npc_actions is not None:
            base["max_npc_actions"] = max_npc_actions
        resolved = InteractOptions.model_validate(base)

        interaction.status = InteractionStatus.RUNNING
        actor_id = interaction.request.actor_id
        message = interaction.request.message or ""

        initial: dict = {
            "message": message,
            "actor_id": actor_id,
            "interaction_id": interaction.id,
            "session_id": session.id,
            "context": {},
            "decision": {},
            "last_rejection": None,
            "last_events": [],
            "speaking_pending": False,
            "step_count": 0,
            "max_steps": resolved.max_steps,
            "max_npc_actions": resolved.max_npc_actions,
            "done": False,
            "status": "running",
            "events": [],
            "dialogue": [],
            "narrative_parts": [],
            "actions": [],
            "trace_steps": [],
            "presentation_pending": False,
            "npc_actions_taken": 0,
            "npc_acted_ids": [],
            "last_executed_actor_id": None,
            "turn_decisions": [],
            "reject_reasons": [],
            "perception_count": 0,
            "memory_count": 0,
            "beliefs_formed": 0,
            "relationship_deltas": [],
        }

        final_state = self.graph.invoke(
            initial,
            config={
                "configurable": {
                    "aether": aether,
                    "world": world,
                    "session": session,
                    "interaction": interaction,
                    "model": self.model,
                    "style": resolved.style,
                    "max_npc_actions": resolved.max_npc_actions,
                    "callbacks": callbacks,
                }
            },
        )

        events = [
            WorldEvent.model_validate(event)
            for event in (final_state.get("events") or [])
        ]
        dialogue = [
            DialogueLine.model_validate(line)
            for line in (final_state.get("dialogue") or [])
        ]
        actions = [
            Action.model_validate(action)
            for action in (final_state.get("actions") or [])
        ]

        interaction.actions = actions
        interaction.events = events
        for step in final_state.get("trace_steps") or []:
            interaction.trace.add_step(step)
        for reason in final_state.get("reject_reasons") or []:
            interaction.trace.add_rejection(reason)

        status_name = final_state.get("status") or "completed"
        try:
            status = InteractionStatus(status_name)
        except ValueError:
            status = InteractionStatus.COMPLETED

        narrative_parts = [
            part.strip()
            for part in (final_state.get("narrative_parts") or [])
            if isinstance(part, str) and part.strip()
        ]
        narrative = "\n\n".join(narrative_parts) if narrative_parts else None

        from aether.ai.continuity import refresh_scene_summary

        scene_summary = refresh_scene_summary(
            world=world,
            session=session,
            actor_id=actor_id,
            events=events,
            narrative=narrative,
            model=self.model,
        )

        event_types = [event.type for event in events]
        speaking_event_types = [
            event_type
            for event_type in event_types
            if event_type in SPEAKING_EVENT_TYPES
        ]
        decisions = [
            TurnDecision.model_validate(item)
            for item in (final_state.get("turn_decisions") or [])
        ]
        npc_action_types = [
            decision.action_type
            for decision in decisions
            if decision.source == "npc_react"
            and decision.accepted is True
            and decision.action_type
        ]
        # Accepted flag may be recorded on a later turn_decisions entry;
        # also count proposed+executed npc actions by type from decisions.
        if not npc_action_types:
            npc_action_types = [
                decision.action_type
                for decision in decisions
                if decision.source == "npc_react" and decision.action_type
            ]
        relationship_deltas = [
            RelationshipDelta.model_validate(item)
            for item in (final_state.get("relationship_deltas") or [])
        ]
        open_questions = unanswered_questions(list(world.events.events))
        report = TurnReport(
            decisions=decisions,
            reject_reasons=list(final_state.get("reject_reasons") or []),
            event_types=event_types,
            speaking_event_types=speaking_event_types,
            dialogue_line_count=len(dialogue),
            npc_action_types=npc_action_types,
            perception_count=int(final_state.get("perception_count") or 0),
            memory_count=int(final_state.get("memory_count") or 0),
            beliefs_formed=int(final_state.get("beliefs_formed") or 0),
            scene_summary=scene_summary,
            relationship_deltas=relationship_deltas,
            open_question_ids=[item.event_id for item in open_questions],
            open_questions=open_questions,
        )

        result = InteractionResult(
            interaction_id=interaction.id,
            status=status,
            dialogue=dialogue,
            narrative=narrative,
            events=events,
            report=report,
        )
        interaction.result = result
        interaction.status = status
        return result
