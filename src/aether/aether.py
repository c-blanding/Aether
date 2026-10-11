from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from pydantic import BaseModel, Field

from aether.ai.aetherai import AetherAI
from aether.cognition.engine import CognitiveEngine
from aether.components.shared import AetherValidationError
from aether.domain.actions import Action
from aether.domain.interactions import Interaction, InteractionResult
from aether.domain.sessions import Session
from aether.domain.world import SimulationResult, World, WorldMetadata
from aether.engine.runtime_engine import RuntimeEngine
from aether.modules.base import AetherModule
from aether.repositories.base import NotFoundError
from aether.repositories.store import InMemoryStore, PostgresStore, Store


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

    def step(self, world: World, action: Action) -> SimulationResult:
        """
        Execute an action, encode witness memories, then persist state.
        """
        result = world.step(action)
        if result.accepted:
            if result.events:
                # Encode minds before persistence so saved world includes new memories.
                self.cognition.encode_events(world, result.events)
                self.store.events.append_many(result.events)
            self.store.worlds.save(world)
            self.worlds[world.id] = world
        return result

    def list_actions(self) -> list[str]:
        return self.engine.list_action_types()

    def interact(
        self,
        world: World,
        session: Session,
        message: str,
        actor_id: str = "player",
        *,
        max_steps: int = 6,
    ) -> InteractionResult:
        """
        Natural-language host entrypoint.

        Runs the act-one LangGraph loop: gather context → decide one action →
        validate → step (+ cognition) → generate narrative (and dialogue when
        speaking) → loop until respond.
        """
        if session.world_id != world.id:
            raise AetherValidationError(
                "Session does not belong to the provided world."
            )
        if session.id not in world.sessions:
            world.sessions[session.id] = session

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
            max_steps=max_steps,
        )

        self.store.worlds.save(world)
        self.worlds[world.id] = world
        return result
