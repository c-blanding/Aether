from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from aether.domain.actions import Action
from aether.domain.character import Character
from aether.domain.interactions import DialogueLine, Interaction
from aether.engine.runtime_engine import RuntimeEngine


class AetherAI:
    def __init__(
        self,
        engine: RuntimeEngine,
        model: BaseChatModel | None = None,
        embeddings: Embeddings | None = None,
        image_model=None,
        voice_model=None,
    ):
        self.engine = engine
        self.model = model
        self.embeddings = embeddings
        self.image_model = image_model
        self.voice_model = voice_model

    def interpret(self, message: str, actor_id: str = "player") -> list[Action]:
        return []

    def generate_dialogue(
        self,
        character: Character,
        interaction: Interaction,
    ) -> list[DialogueLine]:
        return []



