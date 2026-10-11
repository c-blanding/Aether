"""Manor demo: typed steps + NL interact with detective verbs and NPC react."""

from __future__ import annotations

import os
import sys

from aether import Action, Aether, WorldAction
from aether.modules import (
    DetectiveModule,
    DialogueModule,
    InventoryModule,
    NavigationModule,
)

try:
    from aether.ai.model import llm
except Exception:  # noqa: BLE001
    llm = None


def build_manor(aether: Aether):
    world = aether.create_world(
        name="Blackwood Manor",
        description="A mystery mansion full of secrets.",
    )

    library = world.create_location(
        name="Library",
        description="A quiet room filled with old books.",
    )
    study = world.create_location(
        name="Study",
        description="A private study with a heavy oak desk.",
    )
    hall = world.create_location(
        name="Hall",
        description="A long hallway connecting the manor rooms.",
    )

    world.connect_locations(library.id, hall.id)
    world.connect_locations(hall.id, study.id)

    player = world.create_character(
        name="Detective",
        role="Player",
        location_id=library.id,
    )
    arthur = world.create_character(
        name="Arthur",
        role="Butler",
        background="Arthur has served the family for thirty years.",
        location_id=library.id,
    )
    arthur.personality.traits = ["loyal", "secretive", "formal"]
    arthur.personality.speaking_style = "Formal, reserved, and carefully worded."
    arthur.add_goal("Protect the family reputation.", priority=90)
    arthur.learn(
        "No one saw Arthur enter the study.",
        believed_value="true",
        confidence=0.8,
    )
    arthur.remember(
        "Arthur entered the study at midnight and found the victim already dead.",
        importance=0.95,
        emotion="fear",
    )

    old_key = world.create_item(
        name="Old Key",
        description="A brass key with strange initials engraved on it.",
        location_id=library.id,
        tags=["key", "clue"],
    )
    torn_note = world.create_item(
        name="Torn Note",
        description="A scrap that reads: 'midnight — do not trust the butler'.",
        location_id=study.id,
        hidden=True,
        tags=["clue", "note"],
    )

    session = world.create_session(external_player_id="local-demo")
    return (
        world,
        session,
        player,
        arthur,
        old_key,
        torn_note,
        library,
        hall,
        study,
    )


def main() -> None:
    if not os.environ.get("OPENAI_API_KEY") or llm is None:
        print(
            "OPENAI_API_KEY is required for aether.interact.\n"
            "Typed aether.step still works without a model "
            "(see examples/one_room_demo.py)."
        )
        sys.exit(1)

    aether = Aether(model=llm).use(
        InventoryModule(),
        NavigationModule(),
        DialogueModule(),
        DetectiveModule(),
    )

    print("Available actions:", aether.list_actions())

    (
        world,
        session,
        player,
        arthur,
        old_key,
        torn_note,
        library,
        hall,
        study,
    ) = build_manor(aether)

    # Typed path still works.
    move = Action(
        actor_id=player.id,
        data=WorldAction(
            type="move",
            module="navigation",
            parameters={"destination_location_id": hall.id},
        ),
    )
    move_result = aether.step(world, move)
    print("\n--- Typed move to Hall ---")
    print("Accepted:", move_result.accepted, move_result.reason)
    print("Player location:", world.describe_location(player.state.location_id))

    # Return to library for NL demo.
    aether.step(
        world,
        Action(
            actor_id=player.id,
            data=WorldAction(
                type="move",
                module="navigation",
                parameters={"destination_location_id": library.id},
            ),
        ),
    )

    print("\n--- NL: pick up the old key ---")
    pick_result = aether.interact(
        world,
        session,
        "pick up the old key",
        actor_id=player.id,
    )

    
    print("Status:", pick_result.status)
    print("Events:", [e.type for e in pick_result.events])
    print("Narrative:", pick_result.narrative)
    print("Dialogue:", [(d.character_name, d.text) for d in pick_result.dialogue])
    print("Trace:", session.history.latest(1)[0].trace.steps)
    print("Player inventory:", [item.name for item in world.get_character_items(player.id)])

    print("\n--- NL: ask Arthur about the key ---")
    ask_result = aether.interact(
        world,
        session,
        "ask Arthur about the old key",
        actor_id=player.id,
    )
    print("Status:", ask_result.status)
    print("Events:", [e.type for e in ask_result.events])
    print("Narrative:", ask_result.narrative)
    print("Dialogue:")
    for line in ask_result.dialogue:
        print(f"  {line.character_name}: {line.text}")

    print("\n--- NL: go to the study and search it ---")
    search_result = aether.interact(
        world,
        session,
        "go to the study and search it carefully",
        actor_id=player.id,
        max_steps=8,
    )
    print("Status:", search_result.status)
    print("Events:", [e.type for e in search_result.events])
    print("Narrative:", search_result.narrative)
    print("Torn note hidden:", torn_note.hidden)
    print("Trace:", session.history.latest(1)[0].trace.steps)

    if not torn_note.hidden and torn_note.id not in player.inventory.item_ids:
        aether.step(
            world,
            Action(
                actor_id=player.id,
                target_id=torn_note.id,
                data=WorldAction(
                    type="pick_up_item",
                    parameters={"item_id": torn_note.id},
                ),
            ),
        )

    # Return to library with Arthur for evidence presentation.
    if player.state.location_id != library.id:
        # Walk back via hall if needed.
        if player.state.location_id == study.id:
            aether.step(
                world,
                Action(
                    actor_id=player.id,
                    data=WorldAction(
                        type="move",
                        parameters={"destination_location_id": hall.id},
                    ),
                ),
            )
        aether.step(
            world,
            Action(
                actor_id=player.id,
                data=WorldAction(
                    type="move",
                    parameters={"destination_location_id": library.id},
                ),
            ),
        )

    print("\n--- NL: present the torn note to Arthur ---")
    present_result = aether.interact(
        world,
        session,
        "present the torn note to Arthur",
        actor_id=player.id,
    )
    print("Status:", present_result.status)
    print("Events:", [e.type for e in present_result.events])
    print("Narrative:", present_result.narrative)
    print("Dialogue:")
    for line in present_result.dialogue:
        print(f"  {line.character_name}: {line.text}")
    print("Trace:", session.history.latest(1)[0].trace.steps)
    print("Arthur recent memories:")
    for memory in arthur.memory.episodic[-5:]:
        print(f"  - {memory.perspective}")


if __name__ == "__main__":
    main()
