from __future__ import annotations

import unittest
from pathlib import Path

from aether import Action, Aether, PresentationCallbacks, WorldAction
from aether.ai.context import PresentationTone, ScenePayload
from aether.ai.continuity import SceneSummaryDraft
from aether.ai.nodes import _render_narrative, execute_action, generate_dialogue
from aether.ai.state import NextStepDecision
from aether.content import load_scenario
from aether.domain.interactions import unanswered_questions
from aether.domain.presentation import PresentationStyle
from aether.modules import (
    AccessModule,
    ContainerModule,
    DialogueModule,
    InventoryModule,
    NavigationModule,
    SocialModule,
    TimeModule,
)


def _action(actor_id: str, action_type: str, parameters: dict) -> Action:
    return Action(
        actor_id=actor_id,
        data=WorldAction(type=action_type, parameters=parameters),
    )


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _StreamModel:
    def stream(self, messages):
        yield _Chunk("The ")
        yield _Chunk("lamp stays lit.")


class _ScriptedModel:
    schema = None

    def with_structured_output(self, schema, method=None):
        child = _ScriptedModel()
        child.schema = schema
        return child

    def invoke(self, messages):
        name = self.schema.__name__
        if name == "NextStepDecision":
            return NextStepDecision(kind="respond", reason="done")
        if name == "SceneSummaryDraft":
            return SceneSummaryDraft(text="A quiet room.", tension="calm")
        raise AssertionError(name)


class PrivateSpeechTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aether = Aether().use(DialogueModule(), SocialModule())
        self.world = self.aether.create_world(name="Room")
        self.room = self.world.create_location(name="Parlor")
        self.speaker = self.world.create_character(name="Lena", location_id=self.room.id)
        self.friend = self.world.create_character(name="Mara", location_id=self.room.id)
        self.bystander = self.world.create_character(name="Julian", location_id=self.room.id)

    def _step(self, actor_id: str, action_type: str, parameters: dict):
        result = self.aether.step(
            self.world,
            _action(actor_id, action_type, parameters),
        )
        self.assertTrue(result.accepted, result.reason)
        return result

    def test_whisper_is_not_remembered_by_bystanders(self) -> None:
        result = self._step(
            self.speaker.id,
            "whisper",
            {
                "target_character_id": self.friend.id,
                "topic": "the cellar password violet-hour",
            },
        )
        event = result.events[0]
        self.assertEqual(event.type, "dialogue_whispered")
        self.assertNotIn(self.bystander.id, event.witnessed_by)
        self.assertIn(self.friend.id, event.witnessed_by)
        friend_text = " ".join(m.summary for m in self.friend.memory.episodic)
        bystander_text = " ".join(m.summary for m in self.bystander.memory.episodic)
        self.assertIn("violet-hour", friend_text)
        self.assertNotIn("violet-hour", bystander_text)

    def test_lie_and_refuse_leave_distinct_memories(self) -> None:
        self._step(
            self.bystander.id,
            "ask_question",
            {"target_character_id": self.speaker.id, "topic": "the cellar"},
        )
        self._step(
            self.speaker.id,
            "refuse",
            {"questioner_id": self.bystander.id, "topic": "the cellar"},
        )
        self._step(
            self.speaker.id,
            "say_to",
            {
                "target_character_id": self.friend.id,
                "topic": "the alibi",
                "truthfulness": "lie",
            },
        )
        speaker_views = " ".join(m.perspective for m in self.speaker.memory.episodic)
        self.assertIn("I lied about the alibi.", speaker_views)
        self.assertTrue(
            any("lied about the alibi" in b.proposition for b in self.speaker.knowledge.beliefs.values())
        )
        refused = " ".join(m.perspective for m in self.bystander.memory.episodic)
        self.assertIn("refused", refused)
        friend_views = " ".join(m.perspective for m in self.friend.memory.episodic)
        self.assertNotIn("I lied", friend_views)


class MemoryProductTests(unittest.TestCase):
    def test_pin_survives_and_consolidate_does_not_duplicate(self) -> None:
        aether = Aether()
        world = aether.create_world(name="Memory")
        room = world.create_location(name="Room")
        character = world.create_character(name="Mara", location_id=room.id)
        character.add_goal("protect the locket", priority=90)
        character.pin_fact("Her name is Mara.", key="name", kind="name")
        character.remember("Mara will protect the locket.", importance=0.9, participant_ids=["other"])
        for index in range(3):
            character.remember(f"Later beat {index}.", importance=0.2)
        other = world.create_character(name="Lena", location_id=room.id)
        character.update_relationship(other.id, suspicion_delta=0.4)
        character.remember(
            "Lena asked a sharp question.",
            participant_ids=[other.id],
            importance=0.7,
        )

        first = character.memory.consolidate(limit=4)
        second = character.memory.consolidate(limit=4)
        third = character.memory.consolidate(limit=4)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertIsNone(third)
        self.assertEqual(len(character.memory.semantic), 2)

        pack = character.recall_pack("unrelated query", limit=3)
        self.assertIn("Her name is Mara.", pack.pinned)
        self.assertTrue(pack.semantic)
        self.assertLessEqual(len(pack.episodic_lines), 3)
        self.assertTrue(any("locket" in line.lower() for line in pack.goal_relevant))
        self.assertTrue(pack.relationship_colored)


class TurnReportTests(unittest.TestCase):
    def test_open_questions_close_on_answer_or_refuse(self) -> None:
        aether = Aether(model=_ScriptedModel()).use(DialogueModule(), SocialModule())
        world = aether.create_world(name="Questions")
        room = world.create_location(name="Room")
        asker = world.create_character(name="Lena", location_id=room.id)
        other = world.create_character(name="Mara", location_id=room.id)
        session = world.create_session()

        asked = aether.step(
            world,
            _action(asker.id, "ask_question", {
                "target_character_id": other.id,
                "topic": "the missing key",
            }),
            session=session,
        )
        self.assertTrue(asked.accepted, asked.reason)
        open_now = unanswered_questions(world.events.events)
        self.assertEqual([item.topic for item in open_now], ["the missing key"])

        result = aether.interact(
            world,
            session,
            "hello",
            actor_id=asker.id,
            max_npc_actions=0,
            idempotency_key="hello-1",
        )
        self.assertIsNotNone(result.report)
        self.assertEqual(result.report.open_question_ids, [asked.events[0].id])
        self.assertIsNotNone(result.report.scene_summary)

        again = aether.interact(
            world,
            session,
            "hello again",
            actor_id=asker.id,
            idempotency_key="hello-1",
        )
        self.assertEqual(again.interaction_id, result.interaction_id)
        self.assertEqual(len(session.timeline.turns_for_branch("main")), 1)

        refused = aether.step(
            world,
            _action(other.id, "refuse", {
                "questioner_id": asker.id,
                "topic": "the missing key",
            }),
            session=session,
        )
        self.assertTrue(refused.accepted, refused.reason)
        self.assertEqual(unanswered_questions(world.events.events), [])


class StreamingTests(unittest.TestCase):
    def test_narrative_deltas_stream_after_events_exist(self) -> None:
        deltas: list[str] = []
        narrative = _render_narrative(
            model=_StreamModel(),
            message="look",
            events=[{"data": {"type": "item_used"}}],
            scene=ScenePayload(),
            characters=[],
            tone=PresentationTone(style=PresentationStyle()),
            callbacks=PresentationCallbacks(on_narrative_delta=deltas.append),
        )
        self.assertEqual(deltas, ["The ", "lamp stays lit."])
        self.assertEqual(narrative, "The lamp stays lit.")

        called = {"delta": False}

        def _boom(text: str) -> None:
            called["delta"] = True

        generate_dialogue(
            {"last_events": [], "message": "look", "actor_id": "player"},
            {"configurable": {"callbacks": PresentationCallbacks(on_narrative_delta=_boom)}},
        )
        self.assertFalse(called["delta"])

    def test_event_callback_runs_after_step_commits(self) -> None:
        aether = Aether().use(DialogueModule())
        world = aether.create_world(name="Stream")
        room = world.create_location(name="Room")
        speaker = world.create_character(name="Lena", location_id=room.id)
        action = _action(speaker.id, "speak", {"topic": "good evening"})
        order: list[str] = []
        original = aether.step

        def _wrapped(world, step_action, session=None):
            order.append("step")
            return original(world, step_action, session=session)

        aether.step = _wrapped  # type: ignore[method-assign]
        execute_action(
            {
                "decision": {
                    "validated_action": action.model_dump(mode="json"),
                    "source": "planner",
                },
                "actor_id": speaker.id,
                "message": "speak",
                "npc_actions_taken": 0,
                "npc_acted_ids": [],
            },
            {
                "configurable": {
                    "aether": aether,
                    "world": world,
                    "callbacks": PresentationCallbacks(
                        on_event=lambda event: order.append(event.type)
                    ),
                }
            },
        )
        self.assertEqual(order, ["step", "dialogue_spoken"])


class WorldDensityTests(unittest.TestCase):
    def test_scenario_gates_room_and_hides_clue(self) -> None:
        aether = Aether().use(
            InventoryModule(),
            NavigationModule(),
            AccessModule(),
            ContainerModule(),
        )
        path = Path(__file__).resolve().parents[1] / "examples" / "scenarios" / "gated_study.json"
        world = load_scenario(aether, path)
        player = next(iter(world.characters.values()))
        study = next(loc for loc in world.locations.values() if loc.name == "Study")
        key = next(item for item in world.items.values() if item.name == "Brass Key")
        chest = next(item for item in world.items.values() if item.name == "Chest")
        letter = next(item for item in world.items.values() if item.name == "Sealed Letter")
        passage = next(iter(world.passages.values()))

        blocked = aether.step(
            world,
            _action(player.id, "move", {"destination_location_id": study.id}),
        )
        self.assertFalse(blocked.accepted)
        self.assertIn("locked", blocked.reason or "")

        for action_type, parameters in (
            ("pick_up_item", {"item_id": key.id}),
            ("unlock", {"passage_id": passage.id}),
            ("move", {"destination_location_id": study.id}),
            ("open_container", {"container_id": chest.id}),
            ("take_from", {"item_id": letter.id, "container_id": chest.id}),
        ):
            result = aether.step(world, _action(player.id, action_type, parameters))
            self.assertTrue(result.accepted, result.reason)

        self.assertTrue(player.has_item(letter.id))
        self.assertIsNone(letter.state.container_id)

    def test_use_item_keep_and_consume_and_wait_agenda(self) -> None:
        aether = Aether().use(InventoryModule(), TimeModule(), NavigationModule())
        world = aether.create_world(name="Clock")
        parlor = world.create_location(name="Parlor")
        hall = world.create_location(name="Hall")
        world.connect_locations(parlor.id, hall.id)
        player = world.create_character(name="Lena", location_id=parlor.id)
        guest = world.create_character(name="Julian", location_id=parlor.id)
        lamp = world.create_item(name="Lamp", owner_id=player.id, use_mode="keep")
        tonic = world.create_item(name="Tonic", owner_id=player.id, use_mode="consume")
        world.clock.minute_of_day = 8 * 60
        world.add_agenda(guest.id, hall.id, 9 * 60, 12 * 60)

        kept = aether.step(world, _action(player.id, "use_item", {"item_id": lamp.id}))
        self.assertTrue(kept.accepted, kept.reason)
        self.assertTrue(player.has_item(lamp.id))
        self.assertEqual(kept.events[0].data.attributes["effect"], "keep")

        consumed = aether.step(world, _action(player.id, "use_item", {"item_id": tonic.id}))
        self.assertTrue(consumed.accepted, consumed.reason)
        self.assertFalse(player.has_item(tonic.id))
        self.assertTrue(tonic.state.consumed)

        waited = aether.step(world, _action(player.id, "wait", {"minutes": 60}))
        self.assertTrue(waited.accepted, waited.reason)
        self.assertEqual(world.clock.minute_of_day, 9 * 60)
        self.assertEqual(guest.state.location_id, hall.id)


class BranchRestoreTests(unittest.TestCase):
    def test_undo_restores_previous_snapshot(self) -> None:
        aether = Aether().use(InventoryModule())
        world = aether.create_world(name="Undo")
        room = world.create_location(name="Room")
        player = world.create_character(name="Lena", location_id=room.id)
        key = world.create_item(name="Key", location_id=room.id)
        coin = world.create_item(name="Coin", location_id=room.id)
        session = world.create_session()

        def take(item_id: str) -> None:
            result = aether.step(
                world,
                _action(player.id, "pick_up_item", {"item_id": item_id}),
                session=session,
            )
            self.assertTrue(result.accepted, result.reason)
            turn = session.timeline.next_turn(session.current_branch_id)
            session.remember_turn(world, turn)

        take(key.id)
        take(coin.id)
        self.assertTrue(player.has_item(coin.id))

        aether.undo(world, session)
        restored = world.characters[player.id]
        self.assertTrue(restored.has_item(key.id))
        self.assertFalse(restored.has_item(coin.id))
        self.assertEqual(world.items[coin.id].state.location_id, room.id)
        self.assertEqual(len(session.timeline.turns_for_branch("main")), 1)


if __name__ == "__main__":
    unittest.main()
