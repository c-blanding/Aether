from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Any, Iterator

from pydantic import BaseModel, Field

from aether.ai.aetherai import AetherAI
from aether.cognition.engine import CognitiveEngine
from aether.components.shared import AetherValidationError
from aether.components.timeline import Branch
from aether.domain.actions import Action
from aether.domain.interactions import Interaction, InteractionResult
from aether.domain.presentation import (
    InteractOptions,
    PresentationCallbacks,
    PresentationChunk,
    PresentationStyle,
)
from aether.domain.events import EventStore
from aether.domain.snapshot import WorldSnapshot
from aether.domain.sessions import Session
from aether.domain.world import SimulationResult, World, WorldMetadata
from aether.engine.runtime_engine import RuntimeEngine
from aether.modules.base import AetherModule
from aether.modules.social import SocialModule
from aether.repositories.base import DuplicateError, NotFoundError
from aether.repositories.store import InMemoryStore, PostgresStore, Store

if TYPE_CHECKING:
    from langchain_core.embeddings import Embeddings
    from langchain_core.language_models import BaseChatModel

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
        return self.save(world)

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
        Load a world shell from the store, rehydrate characters/sessions/events
        from their tables, reattach the runtime engine, and cache it.
        """
        world = self.store.worlds.get(world_id)
        self._hydrate_world(world)
        world.engine = self.engine
        self.worlds[world.id] = world
        return world

    def save(self, world: World) -> World:
        """
        Persist the world shell and sync related aggregates to their tables.

        - characters → character store (upsert)
        - sessions → session store (upsert)
        - events → event store (append-only; duplicates ignored)

        The worlds document does not embed those aggregates.
        """
        world.state.active_session_ids = list(world.sessions.keys())
        saved = self.store.worlds.save(world)
        self._sync_characters(saved)
        self._sync_sessions(saved)
        self._sync_events(saved)
        self.worlds[saved.id] = saved
        return saved

    def delete_world(self, world_id: str) -> None:
        for character in self.store.characters.list_by_world(world_id):
            self.store.characters.delete(world_id, character.id)
        for session in self.store.sessions.list_by_world(world_id):
            self.store.sessions.delete(session.id)
        self.store.events.delete_by_world(world_id)
        self.store.worlds.delete(world_id)
        self.worlds.pop(world_id, None)

    def _sync_characters(self, world: World) -> None:
        for character in world.characters.values():
            self.store.characters.save(world.id, character)

    def _sync_sessions(self, world: World) -> None:
        for session in world.sessions.values():
            # Keep the active branch tip aligned with the live world so load
            # can restore gameplay state from the session snapshot.
            if session.world_id == world.id:
                session.sync_tip(world)
            self.store.sessions.save(session)

    def _sync_events(self, world: World) -> None:
        for event in world.events.events:
            if event.world_id is None:
                event.world_id = world.id
            try:
                self.store.events.append(event)
            except DuplicateError:
                continue

    def _hydrate_world(self, world: World) -> None:
        """
        Rebuild in-memory aggregates from satellite tables.

        When a session tip snapshot exists, apply it so branch-local character
        and event views win over the append-only event history.
        """
        sessions = self.store.sessions.list_by_world(world.id)
        if sessions:
            world.sessions = {session.id: session for session in sessions}
            world.state.active_session_ids = list(world.sessions.keys())

        for session_id in list(world.state.active_session_ids):
            session = world.sessions.get(session_id)
            if session is None:
                continue
            tip = session.branch_snapshots.get(session.current_branch_id)
            if tip is not None:
                tip.apply_to(world)
                return

        characters = self.store.characters.list_by_world(world.id)
        if characters:
            world.characters = {character.id: character for character in characters}

        stored_events = self.store.events.list_by_world(world.id)
        if stored_events:
            world.events = EventStore(events=list(stored_events))

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
                self._consolidate_after_events(world, result.events)
            # Branch tips are captured by interact/fork/checkout, not each step.
            # Events/sessions/characters are synced via save().
            self.save(world)
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
        self.save(world)
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
        self.save(world)
        return branch

    def undo(
        self,
        world: World,
        session: Session,
    ):
        """
        Drop the latest turn on the active branch and restore its world snapshot.
        """
        self._require_session_world(world, session)
        turn = session.undo_last_turn(world)
        self.save(world)
        return turn

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
        idempotency_key: str | None = None,
        callbacks: PresentationCallbacks | None = None,
    ) -> InteractionResult:
        """
        Natural-language host entrypoint.

        Runs the act-one LangGraph loop: gather context → decide one action →
        validate → step (+ cognition) → generate narrative (and dialogue when
        speaking) → optional NPC reactions → loop until respond.

        Requires a chat model on this SDK instance (``Aether(model=...)``).
        Typed ``aether.step`` still works without a model.

        Presentation can be tuned via ``style=`` or full ``options=``.
        ``callbacks`` fire as committed events, narrative tokens, and dialogue
        lines become available. ``idempotency_key`` returns the previous result
        when the same key is retried on this branch.
        """
        self._require_session_world(world, session)
        if idempotency_key:
            prior = session.interaction_for_key(idempotency_key)
            if prior is not None and prior.result is not None:
                return prior.result

        if self.ai.model is None:
            raise AetherValidationError(
                "Aether.interact requires a language model. "
                "Pass model=... to Aether(...), or use aether.step for typed actions."
            )

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
            idempotency_key=idempotency_key,
        )
        session.history.add(interaction)
        turn = session.timeline.next_turn(
            branch_id=session.current_branch_id,
            interaction_id=interaction.id,
        )
        interaction.trace.add_step(f"Created turn {turn.number}")
        pre_turn = WorldSnapshot.capture(world)

        try:
            result = self.ai.interact(
                self,
                world,
                session,
                interaction,
                options=resolved,
                callbacks=callbacks,
            )
        except Exception:
            pre_turn.apply_to(world)
            session.discard_turn(turn.id, interaction.id)
            self.save(world)
            raise

        if result.events:
            self._stamp_events(session, result.events)
        session.remember_turn(world, turn)
        session.remember_idempotency(interaction)
        interaction.trace.add_step(
            f"Captured branch tip for {session.current_branch_id}"
        )

        self.save(world)
        return result

    def interact_stream(
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
        idempotency_key: str | None = None,
        callbacks: PresentationCallbacks | None = None,
    ) -> Iterator[PresentationChunk]:
        """
        Run ``interact`` and yield presentation chunks as they are produced.

        Event chunks are yielded only after that beat commits. The final chunk
        has ``kind="result"`` and the same ``InteractionResult`` as ``interact``.
        """
        chunks: queue.Queue[PresentationChunk | None] = queue.Queue()
        holder: dict[str, Any] = {}

        def _emit_event(event: Any) -> None:
            if callbacks is not None and callbacks.on_event is not None:
                callbacks.on_event(event)
            chunks.put(PresentationChunk(kind="event", event=event))

        def _emit_delta(text: str) -> None:
            if callbacks is not None and callbacks.on_narrative_delta is not None:
                callbacks.on_narrative_delta(text)
            chunks.put(PresentationChunk(kind="narrative_delta", text=text))

        def _emit_line(line: Any) -> None:
            if callbacks is not None and callbacks.on_dialogue_line is not None:
                callbacks.on_dialogue_line(line)
            chunks.put(PresentationChunk(kind="dialogue_line", dialogue=line))

        stream_callbacks = PresentationCallbacks(
            on_event=_emit_event,
            on_narrative_delta=_emit_delta,
            on_dialogue_line=_emit_line,
        )

        def _run() -> None:
            try:
                holder["result"] = self.interact(
                    world,
                    session,
                    message,
                    actor_id,
                    max_steps=max_steps,
                    style=style,
                    options=options,
                    max_npc_actions=max_npc_actions,
                    idempotency_key=idempotency_key,
                    callbacks=stream_callbacks,
                )
            except Exception as exc:  # noqa: BLE001 — re-raised on the caller thread
                holder["error"] = exc
            finally:
                chunks.put(None)

        worker = threading.Thread(target=_run, daemon=True)
        worker.start()
        while True:
            item = chunks.get()
            if item is None:
                break
            yield item
        worker.join()
        error = holder.get("error")
        if error is not None:
            raise error
        yield PresentationChunk(kind="result", result=holder.get("result"))

    def _consolidate_after_events(self, world: World, events: list[Any]) -> None:
        """Fold a character's new episodes into semantic lore after a busy beat."""
        touched: set[str] = set()
        for event in events:
            if getattr(event, "actor_id", None):
                touched.add(event.actor_id)
            touched.update(getattr(event, "witnessed_by", []) or [])
        for character_id in touched:
            character = world.characters.get(character_id)
            if character is None:
                continue
            done = set(character.memory.consolidated_ids)
            pending = [
                memory
                for memory in character.memory.episodic
                if memory.id not in done
            ]
            if len(pending) >= 4:
                character.memory.consolidate(limit=4)

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

