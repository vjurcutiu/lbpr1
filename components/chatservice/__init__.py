from .http import router as chatservice_router
from .service import InMemoryChatService
from .contracts import (
    IChatService,
    CreateChatRequest,
    ListChatsRequest,
    GetChatRequest,
    ListMessagesRequest,
    PostUserMessageRequest,
    Chat,
    Message,
    Role,
    ChatStatus,
    Envelope,
    ErrorInfo,
)

__all__ = [
    "chatservice_router",
    "InMemoryChatService",
    "IChatService",
    "CreateChatRequest",
    "ListChatsRequest",
    "GetChatRequest",
    "ListMessagesRequest",
    "PostUserMessageRequest",
    "Chat",
    "Message",
    "Role",
    "ChatStatus",
    "Envelope",
    "ErrorInfo",
]

