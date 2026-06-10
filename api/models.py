from typing import Any

from pydantic import BaseModel


class Message(BaseModel):
    """Chat message model."""
    role: str
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str = "helix"
    messages: list[Message]
    temperature: float | None = 0.7
    max_tokens: int | None = None
    stream: bool = False
    conversation_id: str | None = "default"


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int] | None = None
