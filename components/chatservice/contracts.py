from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple

from pydantic import BaseModel, Field, ConfigDict


# ---------- Unified Wire Format (UWF) ----------

class ErrorInfo(BaseModel):
    code: str = Field(..., description="Stable machine code, e.g. 'not_found', 'forbidden', 'invalid_input', 'upstream_error'")
    message: str
    details: Optional[Dict[str, Any]] = None


class Envelope(BaseModel):
    ok: bool
    data: Optional[Any] = None
    error: Optional[ErrorInfo] = None

    @staticmethod
    def success(data: Any) -> "Envelope":
        return Envelope(ok=True, data=data)

    @staticmethod
    def failure(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> "Envelope":
        return Envelope(ok=False, error=ErrorInfo(code=code, message=message, details=details))


# ---------- Domain Models ----------

class ChatStatus(str, Enum):
    active = "active"
    archived = "archived"


class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"


class Citation(BaseModel):
    source_id: str
    title: Optional[str] = None
    score: Optional[float] = None
    uri: Optional[str] = None


class Message(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    chat_id: str
    role: Role
    content: str
    created_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)
    citations: List[Citation] = Field(default_factory=list)


class Chat(BaseModel):
    id: str
    tenant_id: str
    title: str
    status: ChatStatus = ChatStatus.active
    created_at: datetime
    updated_at: datetime


# ---------- Requests ----------

class CreateChatRequest(BaseModel):
    tenant_id: str
    title: Optional[str] = None


class ListChatsRequest(BaseModel):
    tenant_id: str
    cursor: Optional[str] = None
    limit: int = 20


class GetChatRequest(BaseModel):
    tenant_id: str
    chat_id: str


class ListMessagesRequest(BaseModel):
    tenant_id: str
    chat_id: str
    cursor: Optional[str] = None
    limit: int = 50
    order: str = Field(default="asc", pattern="^(asc|desc)$")


class PostUserMessageRequest(BaseModel):
    tenant_id: str
    chat_id: str
    content: str
    stream: bool = False
    retrieval: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)


# ---------- Responses ----------

class CreateChatResponse(BaseModel):
    chat: Chat


class ListChatsResponse(BaseModel):
    items: List[Chat]
    next_cursor: Optional[str] = None


class GetChatResponse(BaseModel):
    chat: Chat
    last_messages: List[Message] = Field(default_factory=list)


class ListMessagesResponse(BaseModel):
    items: List[Message]
    next_cursor: Optional[str] = None


class PostUserMessageResponse(BaseModel):
    user_message: Message
    assistant_message: Optional[Message] = None
    # For streaming mode (future): token stream reference, etc.


# ---------- Ports ----------

class ILLMAdapter(Protocol):
    def generate(self, *, tenant_id: str, messages: List[Message], params: Optional[Dict[str, Any]] = None) -> str: ...


class IRetrievalAdapter(Protocol):
    def retrieve(self, *, tenant_id: str, query: str, top_k: int = 5) -> Tuple[List[str], List[Citation]]: ...


class IChatService(ABC):
    @abstractmethod
    def create_chat(self, req: CreateChatRequest) -> CreateChatResponse: ...

    @abstractmethod
    def list_chats(self, req: ListChatsRequest) -> ListChatsResponse: ...

    @abstractmethod
    def get_chat(self, req: GetChatRequest, last_n: int = 20) -> GetChatResponse: ...

    @abstractmethod
    def list_messages(self, req: ListMessagesRequest) -> ListMessagesResponse: ...

    @abstractmethod
    def post_user_message(self, req: PostUserMessageRequest, llm: ILLMAdapter, retrieval: Optional[IRetrievalAdapter] = None) -> PostUserMessageResponse: ...


# ---------- Errors ----------

class ChatError(Exception):
    code = "chat_error"
    http = 400


class NotFound(ChatError):
    code = "not_found"
    http = 404


class Forbidden(ChatError):
    code = "forbidden"
    http = 403


class InvalidInput(ChatError):
    code = "invalid_input"
    http = 400


class UpstreamError(ChatError):
    code = "upstream_error"
    http = 502

