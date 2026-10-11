from __future__ import annotations

import unittest

from aether import Action, Aether, WorldAction
from aether.modules import InventoryModule
from aether.repositories.serialization import deserialize_world, serialize_world


class SaveSyncTests(unittest.TestCase):
    def test_save_upserts_characters_into_character_store(self) -> None:
        aether = Aether.memory()
        world = aether.create_world(name="Sync Lab")
        location = world.create_location(name="Hall", description="Entry.")
        alice = world.create_character(
            name="Alice",
            role="Guest",
            location_id=location.id,
        )
        bob = world.create_character(
            name="Bob",
            role="Host",
            location_id=location.id,
        )

        aether.save(world)

        stored = aether.store.characters.list_by_world(world.id)
        self.assertEqual({c.id for c in stored}, {alice.id, bob.id})
        self.assertEqual(
            aether.store.characters.get(world.id, alice.id).name,
            "Alice",
        )

    def test_save_persists_sessions_and_events(self) -> None:
        aether = Aether.memory().use(InventoryModule())
        world = aether.create_world(name="Session Lab")
        location = world.create_location(name="Hall", description="Entry.")
        player = world.create_character(
            name="Detective",
            role="Player",
            location_id=location.id,
        )
        key = world.create_item(
            name="Key",
            description="A key.",
            location_id=location.id,
        )
        session = world.create_session()

        result = aether.step(
            world,
            Action(
                actor_id=player.id,
                target_id=key.id,
                data=WorldAction(
                    type="pick_up_item",
                    module="inventory",
                    parameters={"item_id": key.id},
                ),
            ),
            session=session,
        )
        self.assertTrue(result.accepted, result.reason)

        stored_sessions = aether.store.sessions.list_by_world(world.id)
        self.assertEqual(len(stored_sessions), 1)
        self.assertEqual(stored_sessions[0].id, session.id)

        stored_events = aether.store.events.list_by_world(world.id)
        self.assertGreaterEqual(len(stored_events), 1)
        self.assertTrue(any(event.type == "item_picked_up" for event in stored_events))

    def test_world_document_excludes_satellite_aggregates(self) -> None:
        aether = Aether.memory().use(InventoryModule())
        world = aether.create_world(name="Slim Lab")
        location = world.create_location(name="Hall", description="Entry.")
        world.create_character(
            name="Alice",
            role="Guest",
            location_id=location.id,
        )
        world.create_session()
        aether.save(world)

        payload = serialize_world(world)
        self.assertNotIn("characters", payload)
        self.assertNotIn("sessions", payload)
        self.assertNotIn("events", payload)
        self.assertNotIn("engine", payload)

        shell = deserialize_world(payload)
        self.assertEqual(shell.characters, {})
        self.assertEqual(shell.sessions, {})
        self.assertEqual(shell.events.events, [])

    def test_load_world_rehydrates_from_satellite_tables(self) -> None:
        aether = Aether.memory().use(InventoryModule())
        world = aether.create_world(name="Hydrate Lab")
        location = world.create_location(name="Hall", description="Entry.")
        player = world.create_character(
            name="Detective",
            role="Player",
            location_id=location.id,
        )
        key = world.create_item(
            name="Key",
            description="A key.",
            location_id=location.id,
        )
        session = world.create_session()
        aether.step(
            world,
            Action(
                actor_id=player.id,
                target_id=key.id,
                data=WorldAction(
                    type="pick_up_item",
                    module="inventory",
                    parameters={"item_id": key.id},
                ),
            ),
            session=session,
        )

        # Simulate a postgres-style shell document in the world store.
        shell = deserialize_world(serialize_world(world))
        aether.store.worlds.save(shell)
        aether.worlds.clear()

        loaded = aether.load_world(world.id)
        self.assertIn(player.id, loaded.characters)
        self.assertIn(session.id, loaded.sessions)
        self.assertTrue(loaded.characters[player.id].has_item(key.id))
        self.assertTrue(
            any(event.type == "item_picked_up" for event in loaded.events.events)
        )

    def test_delete_world_clears_satellite_stores(self) -> None:
        aether = Aether.memory().use(InventoryModule())
        world = aether.create_world(name="Delete Lab")
        location = world.create_location(name="Hall", description="Entry.")
        player = world.create_character(
            name="Alice",
            role="Guest",
            location_id=location.id,
        )
        key = world.create_item(
            name="Key",
            description="A key.",
            location_id=location.id,
        )
        session = world.create_session()
        aether.step(
            world,
            Action(
                actor_id=player.id,
                target_id=key.id,
                data=WorldAction(
                    type="pick_up_item",
                    module="inventory",
                    parameters={"item_id": key.id},
                ),
            ),
            session=session,
        )

        aether.delete_world(world.id)

        self.assertEqual(aether.store.characters.list_by_world(world.id), [])
        self.assertEqual(aether.store.sessions.list_by_world(world.id), [])
        self.assertEqual(aether.store.events.list_by_world(world.id), [])


if __name__ == "__main__":
    unittest.main()
