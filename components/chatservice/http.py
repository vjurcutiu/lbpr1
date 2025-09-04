from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .contracts import (
    Envelope,
    IChatService,
    CreateChatRequest,
    ListChatsRequest,
    GetChatRequest,
    ListMessagesRequest,
    PostUserMessageRequest,
    ChatError,
)
from .service import InMemoryChatService

logger = logging.getLogger("chatservice.http")
router = APIRouter(prefix="/chats", tags=["chats"])

# --- Dependency wiring (v0.1 simple) ---

_service_singleton = InMemoryChatService()


class FakeLLM:
    provider = "fake-llm"

    def generate(self, *, tenant_id, messages, params=None) -> str:
        # deterministic echo for tests
        # assistant summarizes last user message
        last_user = next((m for m in reversed(messages) if m.role.value == "user"), None)
        txt = last_user.content if last_user else "Hello."
        return f"(assistant) You said: {txt}"


def get_chat_service() -> IChatService:
    return _service_singleton


def get_llm():
    return FakeLLM()


def get_tenant_id(x_tenant_id: str = Query(..., alias="tenant_id")) -> str:
    # In production this comes from AuthService/JWT middleware;
    # for v0.1 accept it as query param to keep edges testable.
    return x_tenant_id


# --- HTTP models for requests (adapters keep edges stable) ---

class CreateChatBody(BaseModel):
    title: str | None = None


class PostMessageBody(BaseModel):
    content: str
    stream: bool = False
    retrieval: bool = False
    metadata: dict = {}


# --- Routes ---

@router.post("", response_model=Envelope)
def create_chat(
    body: CreateChatBody,
    tenant_id: str = Depends(get_tenant_id),
    svc: IChatService = Depends(get_chat_service),
):
    try:
        resp = svc.create_chat(CreateChatRequest(tenant_id=tenant_id, title=body.title))
        return Envelope.success(resp.model_dump())
    except ChatError as e:
        raise HTTPException(status_code=e.http, detail=e.code)


@router.get("", response_model=Envelope)
def list_chats(
    tenant_id: str = Depends(get_tenant_id),
    limit: int = Query(20, ge=1, le=200),
    cursor: str | None = None,
    svc: IChatService = Depends(get_chat_service),
):
    try:
        resp = svc.list_chats(
            ListChatsRequest(tenant_id=tenant_id, cursor=cursor, limit=limit)
        )
        return Envelope.success(resp.model_dump())
    except ChatError as e:
        raise HTTPException(status_code=e.http, detail=e.code)


@router.get("/{chat_id}", response_model=Envelope)
def get_chat(
    chat_id: str,
    tenant_id: str = Depends(get_tenant_id),
    last_n: int = Query(20, ge=0, le=200),
    svc: IChatService = Depends(get_chat_service),
):
    try:
        resp = svc.get_chat(GetChatRequest(tenant_id=tenant_id, chat_id=chat_id), last_n=last_n)
        return Envelope.success(resp.model_dump())
    except ChatError as e:
        raise HTTPException(status_code=e.http, detail=e.code)


@router.get("/{chat_id}/messages", response_model=Envelope)
def list_messages(
    chat_id: str,
    tenant_id: str = Depends(get_tenant_id),
    limit: int = Query(50, ge=1, le=500),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    cursor: str | None = None,
    svc: IChatService = Depends(get_chat_service),
):
    try:
        resp = svc.list_messages(
            ListMessagesRequest(
                tenant_id=tenant_id,
                chat_id=chat_id,
                cursor=cursor,
                limit=limit,
                order=order,
            )
        )
        return Envelope.success(resp.model_dump())
    except ChatError as e:
        raise HTTPException(status_code=e.http, detail=e.code)


@router.post("/{chat_id}/messages", response_model=Envelope)
def post_message(
    chat_id: str,
    body: PostMessageBody,
    tenant_id: str = Depends(get_tenant_id),
    svc: IChatService = Depends(get_chat_service),
    llm = Depends(get_llm),
):
    try:
        resp = svc.post_user_message(
            PostUserMessageRequest(
                tenant_id=tenant_id,
                chat_id=chat_id,
                content=body.content,
                stream=body.stream,
                retrieval=body.retrieval,
                metadata=body.metadata or {},
            ),
            llm=llm,
            retrieval=None,  # hook in future
        )
        return Envelope.success(resp.model_dump())
    except ChatError as e:
        raise HTTPException(status_code=e.http, detail=e.code)

