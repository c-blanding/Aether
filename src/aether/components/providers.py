class LLMProvider:
    def __init__(self, name: str, api_key: str, model: str) -> None:
        self.name = name
        self.api_key = api_key
        self.model = model


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o") -> None:
        super().__init__(name="openai", api_key=api_key, model=model)
