from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from aether.ai.graph import get_interact_graph
from aether.domain.actions import Action
from aether.domain.character import Character
from aether.domain.events import WorldEvent
from aether.domain.interactions import (
    DialogueLine,
    Interaction,
    InteractionResult,
    InteractionStatus,
)
from aether.domain.sessions import Session
from aether.engine.runtime_engine import RuntimeEngine

if TYPE_CHECKING:
    from aether.aether import Aether
    from aether.domain.world import World


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
            self._graph = get_interact_graph()
        return self._graph

    def interpret(self, message: str, actor_id: str = "player") -> list[Action]:
        """Deprecated stub; use interact (act-one loop) instead."""
        return []

    def generate_dialogue(
        self,
        character: Character,
        interaction: Interaction,
    ) -> list[DialogueLine]:
        """Deprecated stub; dialogue is produced inside the interact graph."""
        return []

    def interact(
        self,
        aether: Aether,
        world: World,
        session: Session,
        interaction: Interaction,
        *,
        max_steps: int = 6,
    ) -> InteractionResult:
        """
        Run the act-one LangGraph loop for one player message.
        """
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
            "max_steps": max_steps,
            "done": False,
            "status": "running",
            "events": [],
            "dialogue": [],
            "narrative_parts": [],
            "actions": [],
            "trace_steps": [],
            "presentation_pending": False,
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

        result = InteractionResult(
            interaction_id=interaction.id,
            status=status,
            dialogue=dialogue,
            narrative=narrative,
            events=events,
        )
        interaction.result = result
        interaction.status = status
        return result
