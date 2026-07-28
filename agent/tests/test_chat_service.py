import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

from langgraph.checkpoint.memory import InMemorySaver
from pydantic import SecretStr

from app.agent.events import AgentStreamEvent, MessageEvent
from app.agent.graph import AgentRunResult, RequirementAgent
from app.agent.state import UserContext
from app.agent.service import ChatService
from app.agent.thread_id import build_thread_id
from app.core.config import Settings
from app.rag.indexer import KnowledgeIndexer
from app.schemas.chat import ChatRequest


class FakeAgent:
    def __init__(self) -> None:
        self.thread_ids: list[str] = []
        self.user_contexts: list[UserContext | None] = []

    async def ask(
        self,
        user_message: str,
        thread_id: str,
        user_context: UserContext | None = None,
    ) -> AgentRunResult:
        self.thread_ids.append(thread_id)
        self.user_contexts.append(user_context)
        return AgentRunResult(answer="模拟回答")

    async def stream(
        self,
        user_message: str,
        thread_id: str,
        user_context: UserContext | None = None,
    ) -> AsyncIterator[AgentStreamEvent]:
        self.thread_ids.append(thread_id)
        self.user_contexts.append(user_context)
        yield MessageEvent(content="流式回答")

    async def resume(
        self, thread_id: str, approval: bool
    ) -> AsyncIterator[AgentStreamEvent]:
        self.thread_ids.append(thread_id)
        yield MessageEvent(content=f"确认结果：{approval}")


def create_service(fake_agent: FakeAgent, settings: Settings | None = None) -> ChatService:
    def factory(_: Settings, __: Any, ___: Any, ____: Any) -> RequirementAgent:
        return cast(RequirementAgent, fake_agent)

    return ChatService(
        settings or Settings(), checkpointer=InMemorySaver(), agent_factory=factory
    )


def test_chat_service_builds_isolated_stable_thread_ids() -> None:
    fake_agent = FakeAgent()
    service = create_service(fake_agent)

    async def run() -> None:
        await service.chat(ChatRequest(user_id="user-1", session_id="session-1", message="一"))
        await service.chat(ChatRequest(user_id="user-1", session_id="session-1", message="二"))
        await service.chat(ChatRequest(user_id="user-1", session_id="session-2", message="三"))
        await service.chat(ChatRequest(user_id="user-2", session_id="session-1", message="四"))
        await service.close()

    asyncio.run(run())

    assert fake_agent.thread_ids[0] == fake_agent.thread_ids[1]
    assert len(set(fake_agent.thread_ids)) == 3
    assert fake_agent.thread_ids[0] == build_thread_id("user-1", "session-1")


def test_normal_and_stream_chat_share_thread_and_sse_protocol() -> None:
    fake_agent = FakeAgent()
    service = create_service(fake_agent)

    async def run() -> list[str]:
        request = ChatRequest(user_id="user-1", session_id="session-s", message="第一轮")
        await service.chat(request)
        return [event.type async for event in service.stream_chat(request)]

    event_types = asyncio.run(run())

    assert fake_agent.thread_ids[0] == fake_agent.thread_ids[1]
    assert event_types == ["message", "done"]


def test_nested_demo_user_is_injected_as_graph_user_context() -> None:
    fake_agent = FakeAgent()
    service = create_service(fake_agent)

    async def run() -> None:
        await service.chat(
            ChatRequest.model_validate(
                {
                    "user": {
                        "id": "user_A",
                        "username": "Alice",
                        "roles": ["employee"],
                    },
                    "message": "删除单据 DOC001",
                    "threadId": "demo-thread",
                }
            )
        )

    asyncio.run(run())

    assert fake_agent.thread_ids == ["demo-thread"]
    assert fake_agent.user_contexts == [
        {
            "user_id": "user_A",
            "username": "Alice",
            "roles": ["employee"],
        }
    ]


def test_chat_service_does_not_automatically_rebuild_knowledge_index(
    tmp_path: Path, monkeypatch: Any
) -> None:
    fake_agent = FakeAgent()

    async def forbidden_rebuild(_: KnowledgeIndexer) -> None:
        raise AssertionError("服务启动或聊天时不应自动构建知识索引")

    monkeypatch.setattr(KnowledgeIndexer, "rebuild", forbidden_rebuild)
    service = create_service(
        fake_agent,
        Settings(
            siliconflow_api_key=SecretStr("test-key"),
            chroma_persist_directory=tmp_path / "chroma",
        ),
    )

    async def run() -> None:
        await service.chat(
            ChatRequest(user_id="user-1", session_id="session-index", message="流程规则")
        )
        await service.close()

    asyncio.run(run())
