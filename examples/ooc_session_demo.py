"""Long social session: privacy, memory, doors, containers, time, undo.

Runs without a live language model. Typed steps are the world; the checks at
the end are the consistency bar a host can rely on.
"""

from __future__ import annotations

from aether import Action, Aether, WorldAction
from aether.modules import (
    AccessModule,
    ContainerModule,
    DialogueModule,
    InventoryModule,
    NavigationModule,
    SocialModule,
    TimeModule,
)


def _step(aether: Aether, world, session, actor_id: str, action_type: str, parameters: dict):
    result = aether.step(
        world,
        Action(
            actor_id=actor_id,
            data=WorldAction(
                type=action_type,
                parameters=parameters,
            ),
        ),
        session=session,
    )
    if not result.accepted:
        raise AssertionError(f"{action_type} rejected: {result.reason}")
    turn = session.timeline.next_turn(
        branch_id=session.current_branch_id,
        interaction_id=None,
    )
    session.remember_turn(world, turn)
    return result


def run_session() -> list[str]:
    aether = Aether().use(
        InventoryModule(),
        NavigationModule(),
        DialogueModule(),
        SocialModule(),
        AccessModule(),
        ContainerModule(),
        TimeModule(),
    )
    world = aether.create_world(
        name="Evening Parlor",
        description="A small social scene that stays consistent across a long night.",
    )
    parlor = world.create_location(name="Parlor", description="Lamps and a low table.")
    hall = world.create_location(name="Hall", description="A quiet hall.")
    study = world.create_location(name="Study", description="A desk and a chest.")
    world.connect_locations(parlor.id, hall.id)

    player = world.create_character(name="Lena", role="Guest", location_id=parlor.id)
    mara = world.create_character(
        name="Mara",
        role="Host",
        background="Mara keeps the house and its confidences.",
        location_id=parlor.id,
    )
    julian = world.create_character(
        name="Julian",
        role="Guest",
        location_id=parlor.id,
    )
    mara.add_goal("Learn whether Lena will stay the night.", priority=80)
    player.pin_fact("The host's name is Mara.", key="name", kind="name")

    key = world.create_item(
        name="Brass Key",
        description="Opens the study.",
        location_id=parlor.id,
        tags=["key"],
    )
    lamp = world.create_item(
        name="Lamp",
        description="A small oil lamp.",
        owner_id=player.id,
        use_mode="keep",
    )
    chest = world.create_item(
        name="Chest",
        description="Closed.",
        location_id=study.id,
        is_container=True,
        container_open=False,
    )
    letter = world.create_item(
        name="Folded Letter",
        description="A private note.",
        container_id=chest.id,
        hidden=True,
    )
    passage = world.create_passage(
        hall.id,
        study.id,
        locked=True,
        is_open=True,
        key_item_id=key.id,
    )
    world.add_agenda(julian.id, hall.id, start_minute=9 * 60, end_minute=12 * 60)
    world.clock.minute_of_day = 8 * 60

    session = world.create_session()
    log: list[str] = []

    def beat(title: str, action_type: str, parameters: dict, actor_id: str | None = None):
        _step(aether, world, session, actor_id or player.id, action_type, parameters)
        log.append(f"{len(log) + 1}. {title}")

    beat("Lena greets Mara", "say_to", {
        "target_character_id": mara.id,
        "topic": "a warm hello and thanks for the evening",
        "truthfulness": "truthful",
    })
    beat("Lena asks Mara about staying", "ask_question", {
        "target_character_id": mara.id,
        "topic": "whether Lena should stay the night",
    })
    beat("Lena whispers a secret to Mara", "whisper", {
        "target_character_id": mara.id,
        "topic": "the cellar key phrase violet-hour",
    })
    beat("Lena lies to Julian about the cellar", "say_to", {
        "target_character_id": julian.id,
        "topic": "the cellar is empty",
        "truthfulness": "lie",
    })
    beat("Julian asks Lena about the cellar", "ask_question", {
        "target_character_id": player.id,
        "topic": "what is in the cellar",
    }, actor_id=julian.id)
    beat("Lena refuses Julian", "refuse", {
        "questioner_id": julian.id,
        "topic": "what is in the cellar",
    })
    beat("Mara answers Lena", "answer_question", {
        "questioner_id": player.id,
        "topic": "whether Lena should stay the night",
        "truthfulness": "truthful",
    }, actor_id=mara.id)
    session.pin_fact("Lena and Mara agreed she may stay.", key="agreement", kind="agreement")
    log.append(f"{len(log) + 1}. Session pins the agreement to stay")

    beat("Lena picks up the brass key", "pick_up_item", {"item_id": key.id})
    beat("Lena moves to the hall", "move", {"destination_location_id": hall.id})
    blocked = aether.step(
        world,
        Action(
            actor_id=player.id,
            data=WorldAction(
                type="move",
                parameters={"destination_location_id": study.id},
            ),
        ),
        session=session,
    )
    if blocked.accepted:
        raise AssertionError("Locked study should reject move.")
    log.append(f"{len(log) + 1}. Locked study rejects entry ({blocked.reason})")

    beat("Lena unlocks the study", "unlock", {"passage_id": passage.id})
    beat("Lena enters the study", "move", {"destination_location_id": study.id})
    beat("Lena opens the chest", "open_container", {"container_id": chest.id})
    beat("Lena takes the letter", "take_from", {
        "item_id": letter.id,
        "container_id": chest.id,
    })
    beat("Lena uses the lamp without consuming it", "use_item", {"item_id": lamp.id})
    beat("Lena waits an hour", "wait", {"minutes": 60})

    if world.characters[julian.id].state.location_id != hall.id:
        raise AssertionError("Julian should follow his agenda into the hall.")
    if world.clock.minute_of_day != 9 * 60:
        raise AssertionError("Clock should read 9:00 after the wait.")
    log.append(f"{len(log) + 1}. Julian keeps his 9 o'clock appointment in the hall")

    aether.undo(world, session)
    restored_player = world.characters[player.id]
    restored_mara = world.characters[mara.id]
    restored_julian = world.characters[julian.id]
    if restored_julian.state.location_id != parlor.id:
        raise AssertionError("Undo should put Julian back in the parlor.")
    if world.clock.minute_of_day != 8 * 60:
        raise AssertionError("Undo should rewind the clock.")
    log.append(f"{len(log) + 1}. Undo restores the hour before the wait")

    def _remembered(character, needle: str) -> bool:
        blob = " ".join(
            f"{memory.summary} {memory.perspective}" for memory in character.memory.episodic
        )
        return needle.lower() in blob.lower()

    if not _remembered(restored_mara, "violet-hour"):
        raise AssertionError("Mara should remember the whisper.")
    if _remembered(restored_julian, "violet-hour"):
        raise AssertionError("Julian should not remember a whisper he did not hear.")
    if not _remembered(restored_player, "I lied"):
        raise AssertionError("Lena should remember that she lied.")
    if not _remembered(restored_julian, "refused"):
        raise AssertionError("Julian should remember the refusal.")
    pack = restored_player.recall_pack(
        "evening",
        extra_pinned=[fact.text for fact in session.pinned_facts],
    )
    if "The host's name is Mara." not in pack.pinned:
        raise AssertionError("Pinned name should survive a long session.")
    if "Lena and Mara agreed she may stay." not in pack.pinned:
        raise AssertionError("Session pin should appear in recall packs.")
    if not restored_player.has_item(letter.id) or not restored_player.has_item(lamp.id):
        raise AssertionError("Letter and lamp should still be in Lena's inventory.")
    if restored_mara.relationships.get(player.id).trust <= 0:
        raise AssertionError("A warm greeting should raise Mara's trust.")

    from aether.ai.continuity import SceneSummaryDraft
    from aether.ai.state import NextStepDecision

    class _ScriptedModel:
        schema = None

        def with_structured_output(self, schema, method=None):
            child = _ScriptedModel()
            child.schema = schema
            return child

        def invoke(self, messages):
            name = self.schema.__name__
            if name == "NextStepDecision":
                return NextStepDecision(kind="respond", reason="the evening can rest")
            if name == "SceneSummaryDraft":
                return SceneSummaryDraft(text="The study is quiet.", tension="warm")
            raise AssertionError(f"Unexpected schema {name}")

    aether.ai.model = _ScriptedModel()
    turns_before = len(session.timeline.turns_for_branch(session.current_branch_id))
    first = aether.interact(
        world,
        session,
        "good night",
        actor_id=player.id,
        idempotency_key="good-night",
        max_npc_actions=0,
    )
    second = aether.interact(
        world,
        session,
        "good night again",
        actor_id=player.id,
        idempotency_key="good-night",
        max_npc_actions=0,
    )
    if first.interaction_id != second.interaction_id:
        raise AssertionError("Idempotent retry should return the original result.")
    turns_after = len(session.timeline.turns_for_branch(session.current_branch_id))
    if turns_after != turns_before + 1:
        raise AssertionError("Idempotent retry should not add a second turn.")
    log.append(f"{len(log) + 1}. Retrying the same idempotency key does not double-apply")

    if len(log) < 10:
        raise AssertionError("Demo should cover at least 10 beats.")
    return log


def main() -> None:
    for line in run_session():
        print(line)
    print("World stayed consistent across the session.")


if __name__ == "__main__":
    main()
