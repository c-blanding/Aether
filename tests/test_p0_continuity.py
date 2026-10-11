from __future__ import annotations

import unittest

from aether import Action, Aether, WorldAction
from aether.ai.continuity import heuristic_scene_summary
from aether.ai.graph import clear_interact_graph_cache
from aether.components.planner import ReactivePlanner
from aether.domain.presentation import PresentationStyle, SceneSummary
from aether.modules import (
    DetectiveModule,
    DialogueModule,
    NavigationModule,
    SocialModule,
)


class SceneSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aether = Aether().use(
            DialogueModule(),
            NavigationModule(),
            SocialModule(),
        )
        self.world = self.aether.create_world("Manor", "A quiet manor.")
        self.hall = self.world.create_location("Hall", "Dim hall.")
        self.study = self.world.create_location("Study", "Quiet study.")
        self.hall.connected_location_ids = [self.study.id]
        self.study.connected_location_ids = [self.hall.id]
        self.player = self.world.create_character(
            name="Detective",
            role="Player",
            location_id=self.hall.id,
        )
        self.npc = self.world.create_character(
            name="Butler",
            role="Staff",
            location_id=self.hall.id,
        )
        self.session = self.world.create_session()

    def test_heuristic_summary_tracks_scene(self) -> None:
        result = self.aether.step(
            self.world,
            Action(
                actor_id=self.player.id,
                target_id=self.npc.id,
                data=WorldAction(
                    type="say_to",
                    module="dialogue",
                    parameters={
                        "target_character_id": self.npc.id,
                        "topic": "thank you for your help",
                    },
                ),
            ),
            session=self.session,
        )
        self.assertTrue(result.accepted, result.reason)

        summary = heuristic_scene_summary(
            self.world,
            self.session,
            actor_id=self.player.id,
            events=result.events,
            narrative="The detective thanks the butler.",
        )
        self.assertIn("Hall", summary.text)
        self.assertEqual(summary.location_id, self.hall.id)
        self.assertIn(self.player.id, summary.character_ids)
        self.assertTrue(summary.tension)

    def test_session_persists_scene_summary(self) -> None:
        self.session.scene_summary = SceneSummary(
            text="Earlier, tension hung in the hall.",
            location_id=self.hall.id,
            character_ids=[self.player.id, self.npc.id],
            tension="uneasy",
            open_threads=["Who left the window open?"],
        )
        dumped = self.session.scene_summary.model_dump(mode="json")
        self.assertEqual(
            dumped["text"],
            "Earlier, tension hung in the hall.",
        )
        self.assertEqual(dumped["open_threads"], ["Who left the window open?"])


class SocialRelationshipTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aether = Aether().use(
            DialogueModule(),
            DetectiveModule(),
            SocialModule(),
        )
        self.world = self.aether.create_world("Lab", "Social lab.")
        self.room = self.world.create_location("Parlor", "Warm parlor.")
        self.player = self.world.create_character(
            name="Detective",
            role="Player",
            location_id=self.room.id,
        )
        self.npc = self.world.create_character(
            name="Suspect",
            role="Guest",
            location_id=self.room.id,
        )
        self.letter = self.world.create_item(
            name="Letter",
            description="A damning letter.",
            owner_id=self.player.id,
        )
        self.session = self.world.create_session()

    def test_warm_address_raises_affinity(self) -> None:
        before = self.npc.relationships.get(self.player.id).affinity
        result = self.aether.step(
            self.world,
            Action(
                actor_id=self.player.id,
                target_id=self.npc.id,
                data=WorldAction(
                    type="say_to",
                    module="dialogue",
                    parameters={
                        "target_character_id": self.npc.id,
                        "topic": "thank you, friend",
                    },
                ),
            ),
            session=self.session,
        )
        self.assertTrue(result.accepted, result.reason)
        self.assertTrue(result.relationship_deltas)
        after = self.npc.relationships.get(self.player.id).affinity
        self.assertGreater(after, before)

    def test_evidence_raises_suspicion(self) -> None:
        before = self.npc.relationships.get(self.player.id).suspicion
        result = self.aether.step(
            self.world,
            Action(
                actor_id=self.player.id,
                target_id=self.npc.id,
                data=WorldAction(
                    type="present_evidence",
                    module="detective",
                    parameters={
                        "item_id": self.letter.id,
                        "target_character_id": self.npc.id,
                    },
                ),
            ),
            session=self.session,
        )
        self.assertTrue(result.accepted, result.reason)
        after = self.npc.relationships.get(self.player.id).suspicion
        self.assertGreater(after, before)
        self.assertTrue(
            any(delta.suspicion_delta > 0 for delta in result.relationship_deltas)
        )


class ReactivePlannerV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        clear_interact_graph_cache()
        self.aether = Aether().use(
            DialogueModule(),
            NavigationModule(),
            SocialModule(),
        )
        self.world = self.aether.create_world("Manor", "Reactive manor.")
        self.hall = self.world.create_location("Hall", "Hall.")
        self.kitchen = self.world.create_location("Kitchen", "Kitchen.")
        self.hall.connected_location_ids = [self.kitchen.id]
        self.kitchen.connected_location_ids = [self.hall.id]
        self.player = self.world.create_character(
            name="Detective",
            role="Player",
            location_id=self.hall.id,
        )
        self.npc = self.world.create_character(
            name="Butler",
            role="Staff",
            location_id=self.hall.id,
        )
        self.npc.add_goal("Protect the family reputation.", priority=90)
        self.session = self.world.create_session()

    def test_goal_scoring_prefers_dialogue_when_colocated(self) -> None:
        result = self.aether.step(
            self.world,
            Action(
                actor_id=self.player.id,
                target_id=self.npc.id,
                data=WorldAction(
                    type="ask_question",
                    module="dialogue",
                    parameters={
                        "target_character_ids": [self.npc.id],
                        "topic": "secret about the missing letter",
                    },
                ),
            ),
            session=self.session,
        )
        self.assertTrue(result.accepted, result.reason)

        reaction = ReactivePlanner(importance_threshold=0.5, min_score=0.5).propose(
            self.world,
            player_id=self.player.id,
            recent_events=result.events,
            available_action_types=set(self.aether.list_actions()),
        )
        self.assertIsNotNone(reaction)
        assert reaction is not None
        self.assertIn(reaction.action.type, {"say_to", "speak", "ask_question"})

    def test_withdraw_goal_prefers_move(self) -> None:
        self.npc.goals.active.clear()
        self.npc.add_goal("Withdraw and leave quietly.", priority=95)
        result = self.aether.step(
            self.world,
            Action(
                actor_id=self.player.id,
                target_id=self.npc.id,
                data=WorldAction(
                    type="say_to",
                    module="dialogue",
                    parameters={
                        "target_character_id": self.npc.id,
                        "topic": "I suspect you hid the evidence",
                    },
                ),
            ),
            session=self.session,
        )
        self.assertTrue(result.accepted, result.reason)

        reaction = ReactivePlanner(importance_threshold=0.5, min_score=0.5).propose(
            self.world,
            player_id=self.player.id,
            recent_events=result.events,
            available_action_types=set(self.aether.list_actions()),
        )
        self.assertIsNotNone(reaction)
        assert reaction is not None
        self.assertEqual(reaction.action.type, "move")

    def test_presentation_style_defaults(self) -> None:
        style = PresentationStyle()
        self.assertEqual(style.tone, "literary")
        self.assertEqual(style.length, "default")
        self.assertEqual(style.pov, "third")
        self.assertTrue(style.sfw)

    def test_interact_options_allow_zero_npc_actions(self) -> None:
        from aether.domain.presentation import InteractOptions

        options = InteractOptions.model_validate({"max_npc_actions": 0})
        self.assertEqual(options.max_npc_actions, 0)
        with self.assertRaises(Exception):
            InteractOptions.model_validate({"max_npc_actions": 9})


if __name__ == "__main__":
    unittest.main()
