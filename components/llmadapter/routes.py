from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import StreamingResponse

from .contracts import ChatRequest, ChatResponse, ChatDelta
from .service import LLMAdapterService


router = APIRouter(prefix="/v1/llm", tags=["llm"])


def get_service() -> LLMAdapterService:
    return LLMAdapterService()


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    service: LLMAdapterService = Depends(get_service),
    x_request_id: str | None = Header(default=None, convert_underscores=False),
):
    # Propagate request id if provided
    if x_request_id:
        req.metadata = {**(req.metadata or {}), "request_id": x_request_id}
    return await service.chat(req)


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    service: LLMAdapterService = Depends(get_service),
    x_request_id: str | None = Header(default=None, convert_underscores=False),
):
    if x_request_id:
        req.metadata = {**(req.metadata or {}), "request_id": x_request_id}

    async def ndjson() -> AsyncIterator[bytes]:
        async for delta in service.chat_stream(req):
            yield (json.dumps(delta.dict(exclude_none=True)) + "\n").encode("utf-8")

    # Using text/plain NDJSON for simplicity; can switch to text/event-stream later
    return StreamingResponse(ndjson(), media_type="text/plain; charset=utf-8")


