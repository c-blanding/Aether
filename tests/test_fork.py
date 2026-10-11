from __future__ import annotations

import unittest

from aether import Action, Aether, WorldAction
from aether.components.shared import AetherValidationError
from aether.domain.interactions import Interaction
from aether.modules import InventoryModule


class ForkIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.aether = Aether().use(InventoryModule())
        self.world = self.aether.create_world(
            name="Fork Lab",
            description="Branch isolation fixture.",
        )
        self.library = self.world.create_location(
            name="Library",
            description="Quiet room.",
        )
        self.player = self.world.create_character(
            name="Detective",
            role="Player",
            location_id=self.library.id,
        )
        self.key = self.world.create_item(
            name="Old Key",
            description="Brass key.",
            location_id=self.library.id,
        )
        self.coin = self.world.create_item(
            name="Coin",
            description="A single coin.",
            location_id=self.library.id,
        )
        self.session = self.world.create_session()

    def _pick_up(self, item_id: str) -> None:
        result = self.aether.step(
            self.world,
            Action(
                actor_id=self.player.id,
                target_id=item_id,
                data=WorldAction(
                    type="pick_up_item",
                    module="inventory",
                    parameters={"item_id": item_id},
                ),
            ),
            session=self.session,
        )
        self.assertTrue(result.accepted, result.reason)

    def _record_turn(self, message: str) -> str:
        interaction = Interaction.from_message(
            session_id=self.session.id,
            branch_id=self.session.current_branch_id,
            message=message,
            actor_id=self.player.id,
        )
        self.session.history.add(interaction)
        turn = self.session.timeline.next_turn(
            branch_id=self.session.current_branch_id,
            interaction_id=interaction.id,
        )
        self.session.remember_turn(self.world, turn)
        return turn.id

    def test_fork_isolates_world_mutations(self) -> None:
        self._pick_up(self.key.id)
        turn_id = self._record_turn("pick up key")

        player = self.world.characters[self.player.id]
        self.assertTrue(player.has_item(self.key.id))

        branch = self.aether.fork(self.world, self.session, from_turn_id=turn_id)
        self.assertNotEqual(branch.id, "main")
        self.assertEqual(self.session.current_branch_id, branch.id)

        self._pick_up(self.coin.id)
        self._record_turn("pick up coin on fork")

        forked_player = self.world.characters[self.player.id]
        self.assertTrue(forked_player.has_item(self.key.id))
        self.assertTrue(forked_player.has_item(self.coin.id))

        self.aether.checkout(self.world, self.session, "main")
        self.assertEqual(self.session.current_branch_id, "main")

        main_player = self.world.characters[self.player.id]
        self.assertTrue(main_player.has_item(self.key.id))
        self.assertFalse(main_player.has_item(self.coin.id))
        self.assertIsNone(self.world.items[self.coin.id].state.owner_id)
        self.assertEqual(
            self.world.items[self.coin.id].state.location_id,
            self.library.id,
        )

    def test_fork_from_earlier_turn_restores_that_snapshot(self) -> None:
        self._pick_up(self.key.id)
        first_turn = self._record_turn("pick up key")

        self._pick_up(self.coin.id)
        self._record_turn("pick up coin")

        main_player = self.world.characters[self.player.id]
        self.assertTrue(main_player.has_item(self.key.id))
        self.assertTrue(main_player.has_item(self.coin.id))

        self.aether.fork(self.world, self.session, from_turn_id=first_turn)

        forked_player = self.world.characters[self.player.id]
        self.assertTrue(forked_player.has_item(self.key.id))
        self.assertFalse(forked_player.has_item(self.coin.id))

    def test_history_includes_ancestor_turns_only_to_fork_point(self) -> None:
        self._pick_up(self.key.id)
        first_turn = self._record_turn("pick up key")
        self._pick_up(self.coin.id)
        self._record_turn("pick up coin")

        branch = self.aether.fork(
            self.world,
            self.session,
            from_turn_id=first_turn,
        )
        self._record_turn("say hello on fork")

        history = self.session.history_for_branch(branch.id)
        messages = [item.request.message for item in history]
        self.assertEqual(
            messages,
            ["pick up key", "say hello on fork"],
        )

        main_history = self.session.history_for_branch("main")
        main_messages = [item.request.message for item in main_history]
        self.assertEqual(
            main_messages,
            ["pick up key", "pick up coin"],
        )

    def test_fork_rejects_turn_without_snapshot(self) -> None:
        interaction = Interaction.from_message(
            session_id=self.session.id,
            branch_id=self.session.current_branch_id,
            message="incomplete",
            actor_id=self.player.id,
        )
        self.session.history.add(interaction)
        turn = self.session.timeline.next_turn(
            branch_id=self.session.current_branch_id,
            interaction_id=interaction.id,
        )
        with self.assertRaises(AetherValidationError):
            self.aether.fork(self.world, self.session, from_turn_id=turn.id)

    def test_checkout_same_branch_is_noop_sync(self) -> None:
        self._pick_up(self.key.id)
        self._record_turn("pick up key")
        before = self.session.current_branch_id
        branch = self.aether.checkout(self.world, self.session, before)
        self.assertEqual(branch.id, before)
        self.assertTrue(
            self.world.characters[self.player.id].has_item(self.key.id)
        )


if __name__ == "__main__":
    unittest.main()
