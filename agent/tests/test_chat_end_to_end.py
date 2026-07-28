import asyncio
from typing import Any, cast

import httpx
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.graph import RequirementAgent
from app.agent.service import ChatService
from app.clients.requirement_client import RequirementClient
from app.core.config import Settings
from app.main import create_app
from app.tools.knowledge_tools import KnowledgeTools
from app.tools.requirement_tools import RequirementTools


class ToolCallingModel:
    """模拟模型先选工具、再基于工具结果组织回答。"""

    def __init__(self) -> None:
        self.call_count = 0

    async def ainvoke(self, _: list[BaseMessage]) -> BaseMessage:
        self.call_count += 1
        if self.call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_requirement_by_no",
                        "args": {"requirement_no": "XQ202607001"},
                        "id": "call-e2e-1",
                        "type": "tool_call",
                    }
                ],
            )
        return AIMessage(content="需求 XQ202607001 当前在部门负责人审批节点。")


def test_chat_calls_agent_tool_and_mocked_java_backend() -> None:
    async def java_backend(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/requirements/XQ202607001"
        return httpx.Response(
            200,
            json={
                "success": True,
                "code": "OK",
                "message": "查询成功",
                "data": {
                    "id": 1,
                    "requirementNo": "XQ202607001",
                    "title": "新增生产服务器",
                    "description": "采购两台生产服务器",
                    "applicantId": "U001",
                    "applicantName": "张伟",
                    "department": "信息技术部",
                    "type": "设备采购",
                    "status": "PENDING_APPROVAL",
                    "currentNode": "部门负责人审批",
                    "expectedCompletionDate": "2026-08-15",
                    "createdAt": "2026-07-01T09:00:00+08:00",
                    "updatedAt": "2026-07-03T09:00:00+08:00",
                },
                "traceId": "e2e-trace-001",
            },
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(java_backend))
    client = RequirementClient(Settings(), client=http_client)
    model = cast(Runnable[Any, BaseMessage], ToolCallingModel())
    checkpointer = InMemorySaver()
    agent = RequirementAgent(
        model, RequirementTools(client), KnowledgeTools(None), checkpointer
    )

    def factory(
        _: Settings, __: RequirementTools, ___: KnowledgeTools, ____: Any
    ) -> RequirementAgent:
        return agent

    app = create_app(
        ChatService(Settings(), checkpointer=checkpointer, agent_factory=factory)
    )

    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as api_client:
            return await api_client.post(
                "/chat/sync",
                json={
                    "userId": "user-001",
                    "sessionId": "session-001",
                    "message": "查询 XQ202607001",
                },
            )

    response = asyncio.run(request())
    asyncio.run(http_client.aclose())

    assert response.status_code == 200
    assert response.json()["answer"] == "需求 XQ202607001 当前在部门负责人审批节点。"
