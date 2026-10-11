from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from aether.ai.aetherai import AetherAI
from aether.cognition.engine import CognitiveEngine
from aether.components.shared import AetherValidationError
from aether.components.timeline import Branch
from aether.domain.actions import Action
from aether.domain.interactions import Interaction, InteractionResult
from aether.domain.presentation import InteractOptions, PresentationStyle
from aether.domain.sessions import Session
from aether.domain.world import SimulationResult, World, WorldMetadata
from aether.engine.runtime_engine import RuntimeEngine
from aether.modules.base import AetherModule
from aether.modules.social import SocialModule
from aether.repositories.base import NotFoundError
from aether.repositories.store import InMemoryStore, PostgresStore, Store

World.model_rebuild()



class AetherConfig(BaseModel):
    """
    Configuration for the Aether SDK runtime.
    """

    environment: str = Field(
        default="development",
        description="Runtime environment name.",
        examples=["development", "staging", "production"],
    )

    debug: bool = Field(
        default=True,
        description="Whether debug mode is enabled.",
    )



class Aether:
    """
    AI simulation SDK for building persistent, intelligent characters
    and evolving interactive worlds.
    """

    def __init__(
        self,
        store: Store | None = None,
        model: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
    ) -> None:
        self.store = store or InMemoryStore()
        self.engine = RuntimeEngine()
        self.cognition = CognitiveEngine()
        self.worlds: dict[str, World] = {}
        self.ai = AetherAI(
            engine=self.engine,
            model=model,
            embeddings=embeddings,
        )
        self.configuration = AetherConfig()


    @classmethod
    def memory(
        cls,
        model: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
    ) -> Aether:
        """Create an SDK instance with the default in-memory store."""
        return cls(store=InMemoryStore(), model=model, embeddings=embeddings)

    @classmethod
    def postgres(
        cls,
        *,
        apply_migrations: bool = False,
        model: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
    ) -> Aether:
        """
        Create an SDK instance backed by Neon/Postgres.

        Requires ``DATABASE_URL``. Set ``apply_migrations=True`` to run
        ``schema.sql`` on startup.
        """
        return cls(
            store=PostgresStore(apply_migrations=apply_migrations),
            model=model,
            embeddings=embeddings,
        )

    def use(self, *modules: AetherModule) -> Aether:
        for module in modules:
            self.engine.register_module(module)
        return self

    def create_world(
        self,
        name: str,
        description: str = "",
    ) -> World:
        world = World(
            metadata=WorldMetadata(
                name=name,
                description=description,
            ),
            engine=self.engine,
        )
        self.store.worlds.save(world)
        self.worlds[world.id] = world
        return world

    def get_world(self, world_id: str) -> World:
        world = self.worlds.get(world_id)
        if world is not None:
            return world

        try:
            return self.load_world(world_id)
        except NotFoundError as exc:
            raise AetherValidationError(f"World not found: {world_id}") from exc

    def load_world(self, world_id: str) -> World:
        """
        Load a world from the store, reattach the runtime engine,
        and cache it on this SDK instance.
        """
        world = self.store.worlds.get(world_id)
        world.engine = self.engine
        self.worlds[world.id] = world
        return world

    def save(self, world: World) -> World:
        """Persist the current world snapshot to the store."""
        saved = self.store.worlds.save(world)
        self.worlds[saved.id] = saved
        return saved

    def delete_world(self, world_id: str) -> None:
        self.store.worlds.delete(world_id)
        self.worlds.pop(world_id, None)

    def step(
        self,
        world: World,
        action: Action,
        session: Session | None = None,
    ) -> SimulationResult:
        """
        Execute an action, encode witness memories, then persist state.

        When ``session`` is provided, events are stamped with the active
        branch and the session tip snapshot is updated.
        """
        result = world.step(action)
        if result.accepted:
            if result.events:
                if session is not None:
                    self._stamp_events(session, result.events)
                # Encode minds before persistence so saved world includes new memories.
                cognitive = self.cognition.encode_events(world, result.events)
                relationship_deltas = []
                if self.engine.modules.is_installed("social"):
                    social = self.engine.modules.get("social")
                    if isinstance(social, SocialModule):
                        relationship_deltas = social.apply_outcomes(
                            world, result.events
                        )
                result = result.model_copy(
                    update={
                        "perception_count": len(cognitive.perceptions),
                        "memory_count": len(cognitive.memories),
                        "beliefs_formed": len(cognitive.beliefs),
                        "relationship_deltas": relationship_deltas,
                    }
                )
                self.store.events.append_many(result.events)
            # Branch tips are captured by interact/fork/checkout, not each step.
            self.store.worlds.save(world)
            self.worlds[world.id] = world
        return result

    def list_actions(self) -> list[str]:
        return self.engine.list_action_types()

    def fork(
        self,
        world: World,
        session: Session,
        from_turn_id: str | None = None,
    ) -> Branch:
        """
        Fork the session timeline into an isolated branch and restore its world.

        The live ``world`` becomes the forked branch's simulation state.
        Parent branch tip is preserved in ``session.branch_snapshots``.
        """
        self._require_session_world(world, session)
        branch = session.branch(world, from_turn_id=from_turn_id)
        self.store.worlds.save(world)
        self.worlds[world.id] = world
        return branch

    def checkout(
        self,
        world: World,
        session: Session,
        branch_id: str,
    ) -> Branch:
        """
        Switch the active branch, saving the current tip and restoring the target.
        """
        self._require_session_world(world, session)
        branch = session.checkout(world, branch_id)
        self.store.worlds.save(world)
        self.worlds[world.id] = world
        return branch

    def interact(
        self,
        world: World,
        session: Session,
        message: str,
        actor_id: str = "player",
        *,
        max_steps: int = 6,
        style: PresentationStyle | None = None,
        options: InteractOptions | None = None,
        max_npc_actions: int | None = None,
    ) -> InteractionResult:
        """
        Natural-language host entrypoint.

        Runs the act-one LangGraph loop: gather context → decide one action →
        validate → step (+ cognition) → generate narrative (and dialogue when
        speaking) → optional NPC reactions → loop until respond.

        Requires a chat model on this SDK instance (``Aether(model=...)``).
        Typed ``aether.step`` still works without a model.

        Presentation can be tuned via ``style=`` or full ``options=``.
        """
        if self.ai.model is None:
            raise AetherValidationError(
                "Aether.interact requires a language model. "
                "Pass model=... to Aether(...), or use aether.step for typed actions."
            )
        self._require_session_world(world, session)

        base = (options or InteractOptions()).model_dump()
        if options is None:
            base["max_steps"] = max_steps
        if style is not None:
            base["style"] = style
        if max_npc_actions is not None:
            base["max_npc_actions"] = max_npc_actions
        resolved = InteractOptions.model_validate(base)

        interaction = Interaction.from_message(
            session_id=session.id,
            branch_id=session.current_branch_id,
            message=message,
            actor_id=actor_id,
        )
        session.history.add(interaction)
        turn = session.timeline.next_turn(
            branch_id=session.current_branch_id,
            interaction_id=interaction.id,
        )
        interaction.trace.add_step(f"Created turn {turn.number}")

        result = self.ai.interact(
            self,
            world,
            session,
            interaction,
            options=resolved,
        )

        if result.events:
            self._stamp_events(session, result.events)
        session.remember_turn(world, turn)
        interaction.trace.add_step(
            f"Captured branch tip for {session.current_branch_id}"
        )

        self.store.worlds.save(world)
        self.worlds[world.id] = world
        return result

    def _require_session_world(self, world: World, session: Session) -> None:
        if session.world_id != world.id:
            raise AetherValidationError(
                "Session does not belong to the provided world."
            )
        if session.id not in world.sessions:
            world.sessions[session.id] = session

    @staticmethod
    def _stamp_events(session: Session, events: list[Any]) -> None:
        for event in events:
            if getattr(event, "session_id", None) is None:
                event.session_id = session.id
            if getattr(event, "branch_id", None) is None:
                event.branch_id = session.current_branch_id

