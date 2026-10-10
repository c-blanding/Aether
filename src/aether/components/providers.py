from pydantic import BaseModel


class LLMProvider(BaseModel):
    name: str
    api_key: str
    model: str

class OpenAIProvider(LLMProvider):
    name: str = "openai"
    api_key: str
    model: str = "gpt-4o"

