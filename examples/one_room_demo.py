from aether import Action, Aether, WorldAction
from aether.modules import InventoryModule


aether = Aether().use(InventoryModule())

print("Available actions:", aether.list_actions())

world = aether.create_world(
    name="Blackwood Manor",
    description="A mystery mansion full of secrets.",
)

library = world.create_location(
    name="Library",
    description="A quiet room filled with old books.",
)

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

arthur.add_goal(
    "Protect the family reputation.",
    priority=90,
)

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
)

action = Action(
    actor_id=player.id,
    target_id=old_key.id,
    data=WorldAction(
        type="pick_up_item",
        module="inventory",
        parameters={
            "item_id": old_key.id,
        },
    ),
)

result = aether.step(world, action)

print("Accepted:", result.accepted)
print("Reason:", result.reason)
print("Events:", result.events)
print("Player inventory:", player.inventory.item_ids)
print("Player memory:", [m.perspective for m in player.memory.episodic])
print("Arthur memory:", [m.perspective for m in arthur.memory.episodic])
print(
    "Player beliefs:",
    [b.proposition for b in player.knowledge.beliefs.values()],
)
print(
    "Arthur beliefs:",
    [b.proposition for b in arthur.knowledge.beliefs.values()],
)
