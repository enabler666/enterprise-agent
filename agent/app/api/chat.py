"""普通聊天与 SSE 流式聊天路由。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.agent.events import AgentStreamEvent
from app.agent.service import ChatService
from app.core.exceptions import AgentConfigurationError
from app.schemas.chat import ChatRequest, ChatResponse, ChatResumeRequest

router = APIRouter(tags=["chat"])


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(payload: ChatRequest, request: Request) -> ChatResponse:
    """将用户消息交给需求 Agent；路由层不处理工具或模型流程。"""
    service: ChatService = request.app.state.chat_service
    try:
        return await service.chat(payload)
    except AgentConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


def _encode_sse(event: AgentStreamEvent) -> str:
    data = asdict(event)
    event_type = str(data.pop("type"))
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {payload}\n\n"


def _stream_response(event_source: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        event_source,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat")
@router.post("/chat/stream", include_in_schema=False)
async def stream_chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    """发起 Agent 并输出 SSE；/chat/stream 仅作为旧客户端兼容别名。"""
    service: ChatService = request.app.state.chat_service

    async def event_source() -> AsyncIterator[str]:
        async for event in service.stream_chat(payload):
            yield _encode_sse(event)

    return _stream_response(event_source())


@router.post("/chat/resume")
async def resume_chat(payload: ChatResumeRequest, request: Request) -> StreamingResponse:
    """使用原 thread_id 和 Command(resume=...) 恢复暂停的 LangGraph。"""
    service: ChatService = request.app.state.chat_service

    async def event_source() -> AsyncIterator[str]:
        async for event in service.resume_chat(payload):
            yield _encode_sse(event)

    return _stream_response(event_source())
