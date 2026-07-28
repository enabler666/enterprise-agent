import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.agent.events import AgentStreamEvent, DoneEvent, MessageEvent, StatusEvent
from app.core.exceptions import AgentConfigurationError
from app.main import create_app
from app.schemas.chat import ChatRequest, ChatResponse, ChatResumeRequest


class FakeChatService:
    def __init__(self, configuration_error: bool = False) -> None:
        self.configuration_error = configuration_error
        self.requests: list[ChatRequest] = []
        self.closed = False

    async def start(self) -> None:
        pass

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if self.configuration_error:
            raise AgentConfigurationError("未配置 DEEPSEEK_API_KEY，无法调用需求 Agent")
        self.requests.append(request)
        return ChatResponse(
            answer=f"已收到：{request.message}",
            user_id=request.resolved_user_id,
            session_id=request.session_id or request.thread_id,
        )

    async def close(self) -> None:
        self.closed = True

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[AgentStreamEvent]:
        self.requests.append(request)
        yield StatusEvent()
        yield MessageEvent(content="模拟")
        yield MessageEvent(content="回答")
        yield DoneEvent()

    async def resume_chat(
        self, request: ChatResumeRequest
    ) -> AsyncIterator[AgentStreamEvent]:
        yield MessageEvent(content=f"approval={str(request.approval).lower()}")
        yield DoneEvent()


def test_chat_returns_answer_and_uses_camel_case_contract() -> None:
    service = FakeChatService()
    app = create_app(service)

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat/sync",
                json={"userId": "user-001", "sessionId": "session-001", "message": "查询需求"},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.json() == {
        "answer": "已收到：查询需求",
        "userId": "user-001",
        "sessionId": "session-001",
    }
    assert service.requests[0].user_id == "user-001"


def test_chat_rejects_blank_message() -> None:
    app = create_app(FakeChatService())

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat/sync",
                json={"userId": "user-001", "sessionId": "session-001", "message": "  "},
            )

    assert asyncio.run(request()).status_code == 422


def test_chat_returns_clear_error_when_agent_configuration_is_missing() -> None:
    app = create_app(FakeChatService(configuration_error=True))

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat/sync",
                json={"userId": "user-001", "sessionId": "session-001", "message": "查询需求"},
            )

    response = asyncio.run(request())

    assert response.status_code == 503
    assert response.json()["detail"] == "未配置 DEEPSEEK_API_KEY，无法调用需求 Agent"


def test_stream_chat_returns_typed_sse_events() -> None:
    service = FakeChatService()
    app = create_app(service)

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                json={"userId": "user-1", "sessionId": "session-1", "message": "查询需求"},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    blocks = [block for block in response.text.split("\n\n") if block]
    assert [block.splitlines()[0] for block in blocks] == [
        "event: status",
        "event: message",
        "event: message",
        "event: done",
    ]
    assert json.loads(blocks[1].splitlines()[1].removeprefix("data: "))["content"] == "模拟"


def test_resume_chat_returns_sse() -> None:
    app = create_app(FakeChatService())

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat/resume",
                json={"threadId": "delete-thread", "approval": True},
            )

    response = asyncio.run(request())

    assert response.status_code == 200
    assert "event: message" in response.text
    assert "approval=true" in response.text
    assert "event: done" in response.text
