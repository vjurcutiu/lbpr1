from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from .contracts import (
    Chat,
    ChatStatus,
    IChatService,
    ILLMAdapter,
    IRetrievalAdapter,
    ListChatsRequest,
    ListChatsResponse,
    GetChatRequest,
    GetChatResponse,
    ListMessagesRequest,
    ListMessagesResponse,
    Message,
    PostUserMessageRequest,
    PostUserMessageResponse,
    Role,
    CreateChatRequest,
    CreateChatResponse,
    NotFound,
    Forbidden,
    InvalidInput,
    UpstreamError,
)

logger = logging.getLogger("chatservice")
logger.setLevel(logging.INFO)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryChatService(IChatService):
    """
    Simple, deterministic in-memory implementation for tests and local dev.
    Tenants are isolated by tenant_id at method boundaries (no cross-tenant visibility).
    """

    def __init__(self) -> None:
        # storage
        self._chats: Dict[str, Chat] = {}
        self._messages_by_chat: Dict[str, List[Message]] = {}
        # simple per-tenant index
        self._tenant_chat_ids: Dict[str, List[str]] = {}

    # --- helpers ---

    def _require_chat(self, tenant_id: str, chat_id: str) -> Chat:
        chat = self._chats.get(chat_id)
        if not chat:
            raise NotFound("chat not found")
        if chat.tenant_id != tenant_id:
            raise Forbidden("tenant mismatch")
        return chat

    def _new_id(self) -> str:
        return uuid.uuid4().hex

    # --- IChatService ---

    def create_chat(self, req: CreateChatRequest) -> CreateChatResponse:
        if not req.tenant_id:
            raise InvalidInput("tenant_id required")
        chat_id = self._new_id()
        now = _now()
        title = req.title or "New Chat"
        chat = Chat(
            id=chat_id,
            tenant_id=req.tenant_id,
            title=title,
            status=ChatStatus.active,
            created_at=now,
            updated_at=now,
        )
        self._chats[chat_id] = chat
        self._messages_by_chat[chat_id] = []
        self._tenant_chat_ids.setdefault(req.tenant_id, []).insert(0, chat_id)

        logger.info(
            "chat.create",
            extra={"tenant_id": req.tenant_id, "chat_id": chat_id, "title": title},
        )
        return CreateChatResponse(chat=chat)

    def list_chats(self, req: ListChatsRequest) -> ListChatsResponse:
        ids = self._tenant_chat_ids.get(req.tenant_id, [])
        # naive pagination for v0.1
        items = [self._chats[cid] for cid in ids][: req.limit]
        logger.info(
            "chat.list",
            extra={"tenant_id": req.tenant_id, "count": len(items)},
        )
        return ListChatsResponse(items=items, next_cursor=None)

    def get_chat(self, req: GetChatRequest, last_n: int = 20) -> GetChatResponse:
        chat = self._require_chat(req.tenant_id, req.chat_id)
        msgs = self._messages_by_chat.get(chat.id, [])
        last_messages = msgs[-last_n:] if last_n > 0 else []
        logger.info(
            "chat.get",
            extra={"tenant_id": req.tenant_id, "chat_id": chat.id, "last_n": last_n, "messages": len(last_messages)},
        )
        return GetChatResponse(chat=chat, last_messages=last_messages)

    def list_messages(self, req: ListMessagesRequest) -> ListMessagesResponse:
        chat = self._require_chat(req.tenant_id, req.chat_id)
        msgs = list(self._messages_by_chat.get(chat.id, []))
        if req.order == "desc":
            msgs = list(reversed(msgs))
        items = msgs[: req.limit]
        logger.info(
            "chat.messages.list",
            extra={"tenant_id": req.tenant_id, "chat_id": chat.id, "count": len(items), "order": req.order},
        )
        return ListMessagesResponse(items=items, next_cursor=None)

    def post_user_message(
        self,
        req: PostUserMessageRequest,
        llm: ILLMAdapter,
        retrieval: Optional[IRetrievalAdapter] = None,
    ) -> PostUserMessageResponse:
        chat = self._require_chat(req.tenant_id, req.chat_id)
        if not req.content or not req.content.strip():
            raise InvalidInput("content required")

        user_msg = Message(
            id=self._new_id(),
            chat_id=chat.id,
            role=Role.user,
            content=req.content,
            created_at=_now(),
            metadata=req.metadata or {},
            citations=[],
        )
        self._messages_by_chat[chat.id].append(user_msg)

        # Retrieval hook (optional)
        context_snippets: List[str] = []
        citations = []
        if retrieval and req.retrieval:
            try:
                context_snippets, citations = retrieval.retrieve(
                    tenant_id=req.tenant_id, query=req.content, top_k=5
                )
            except Exception as e:
                logger.exception("retrieval.failed")
                raise UpstreamError(f"retrieval failed: {e}") from e

        # Prepare LLM messages (simple map: all past messages)
        messages_for_llm = list(self._messages_by_chat[chat.id])
        if context_snippets:
            # Prepend a synthetic tool/context message (v0.1 simple approach)
            context_msg = Message(
                id=self._new_id(),
                chat_id=chat.id,
                role=Role.tool,
                content="\n\n".join(context_snippets),
                created_at=_now(),
                metadata={"kind": "retrieval_context"},
                citations=citations,
            )
            self._messages_by_chat[chat.id].append(context_msg)
            messages_for_llm.append(context_msg)

        # Generate assistant response (sync v0.1)
        try:
            text = llm.generate(tenant_id=req.tenant_id, messages=messages_for_llm, params=None)
        except Exception as e:
            logger.exception("llm.failed")
            raise UpstreamError(f"llm failed: {e}") from e

        asst_msg = Message(
            id=self._new_id(),
            chat_id=chat.id,
            role=Role.assistant,
            content=text,
            created_at=_now(),
            metadata={"provider": getattr(llm, "provider", "unknown")},
            citations=citations,
        )
        self._messages_by_chat[chat.id].append(asst_msg)

        # Touch chat updated_at
        self._chats[chat.id] = chat.model_copy(update={"updated_at": _now()})

        logger.info(
            "chat.messages.create",
            extra={
                "tenant_id": req.tenant_id,
                "chat_id": chat.id,
                "user_message_id": user_msg.id,
                "assistant_message_id": asst_msg.id,
                "retrieval": bool(retrieval and req.retrieval),
            },
        )

        return PostUserMessageResponse(user_message=user_msg, assistant_message=asst_msg)
