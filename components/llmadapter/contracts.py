from __future__ import annotations

import enum
from typing import Any, Dict, Iterable, List, Literal, Optional, AsyncIterator, Union
from pydantic import BaseModel, Field, validator


# ===== Errors (domain) =====

class LLMError(Exception):
    """Base class for LLM adapter errors."""


class ProviderError(LLMError):
    pass


class RateLimitError(LLMError):
    pass


class InvalidRequestError(LLMError):
    pass


class AuthError(LLMError):
    pass


class TimeoutError(LLMError):
    pass


# ===== Contracts (schemas) =====

Role = Literal["system", "user", "assistant", "tool"]


class ToolParam(BaseModel):
    name: str
    description: Optional[str] = None
    schema: Dict[str, Any] = Field(
        default_factory=dict, description="JSON Schema for tool parameters"
    )


class ToolSpec(BaseModel):
    name: str
    description: Optional[str] = None
    parameters: Optional[ToolParam] = None


class ToolCall(BaseModel):
    id: Optional[str] = None
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class PromptMessage(BaseModel):
    role: Role
    content: str
    name: Optional[str] = None
    # For tool message replies we can thread by tool_call_id if needed
    tool_call_id: Optional[str] = None

    @validator("content")
    def content_not_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("content must be a non-empty string")
        return v


class ChatRequest(BaseModel):
    model: str = Field(..., description="Provider-specific model name")
    messages: List[PromptMessage]
    temperature: Optional[float] = Field(default=0.2, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, gt=0)
    stop: Optional[List[str]] = None
    tools: Optional[List[ToolSpec]] = None
    tool_choice: Optional[Literal["auto", "none"]] = "none"
    metadata: Dict[str, Any] = Field(default_factory=dict)  # tracing, tenant, etc.

    @validator("messages")
    def at_least_one_message(cls, v: List[PromptMessage]) -> List[PromptMessage]:
        if not v:
            raise ValueError("messages must contain at least one message")
        return v


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatResponseChoice(BaseModel):
    index: int = 0
    message: PromptMessage
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None


class ChatResponse(BaseModel):
    id: str
    model: str
    choices: List[ChatResponseChoice]
    usage: Usage = Field(default_factory=Usage)
    provider: Optional[str] = None
    request_id: Optional[str] = None
    span_id: Optional[str] = None


# Streaming delta frame
class ChatDelta(BaseModel):
    id: Optional[str] = None
    model: Optional[str] = None
    content_delta: Optional[str] = None
    tool_calls_delta: Optional[List[ToolCall]] = None
    usage: Optional[Usage] = None
    event: Optional[Literal["chunk", "end"]] = "chunk"


# ===== Port interface =====

class LLMProvider:
    """
    Provider port with normalized signatures.
    Implementations must be side-effect free beyond network calls
    and should avoid global state for testability.
    """

    name: str = "unknown"

    async def generate(self, req: ChatRequest) -> ChatResponse:
        raise NotImplementedError

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        raise NotImplementedError


