"""聊天服务：连接 FastAPI 请求与持久化需求 Agent。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent.events import (
    AgentStreamEvent,
    DoneEvent,
    ErrorEvent,
    HumanActionRequiredEvent,
)
from app.agent.graph import AgentRunResult, RequirementAgent, build_requirement_agent
from app.agent.state import UserContext
from app.agent.thread_id import build_thread_id
from app.clients.requirement_client import RequirementClient
from app.core.config import Settings
from app.core.exceptions import AgentConfigurationError
from app.rag.embedding import SiliconFlowEmbeddingProvider
from app.rag.retriever import KnowledgeRetriever
from app.rag.vector_store import ChromaVectorStore
from app.schemas.chat import ChatRequest, ChatResponse, ChatResumeRequest
from app.tools.knowledge_tools import KnowledgeTools
from app.tools.requirement_tools import RequirementTools


class RequirementAgentFactory(Protocol):
    def __call__(
        self,
        settings: Settings,
        requirement_tools: RequirementTools,
        knowledge_tools: KnowledgeTools,
        checkpointer: BaseCheckpointSaver[Any],
    ) -> RequirementAgent: ...


class ChatService:
    """处理聊天请求，线程级状态由 LangGraph Checkpointer 统一维护。"""

    def __init__(
        self,
        settings: Settings,
        checkpointer: BaseCheckpointSaver[Any] | None = None,
        agent_factory: RequirementAgentFactory = build_requirement_agent,
    ) -> None:
        self._settings = settings
        self._checkpointer = checkpointer
        self._checkpointer_context: AbstractAsyncContextManager[
            AsyncSqliteSaver
        ] | None = None
        self._agent_factory = agent_factory
        self._client: RequirementClient | None = None
        self._embedding_provider: SiliconFlowEmbeddingProvider | None = None
        self._agent: RequirementAgent | None = None

    async def chat(self, request: ChatRequest) -> ChatResponse:
        thread_id = self._request_thread_id(request)
        result = await self._get_agent().ask(
            request.message,
            thread_id=thread_id,
            user_context=self._user_context(request),
        )
        return ChatResponse(
            answer=result.answer,
            user_id=request.resolved_user_id,
            session_id=request.session_id or thread_id,
        )

    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[AgentStreamEvent]:
        """流式执行一轮聊天；Graph 节点 checkpoint 与 SSE 事件相互独立。"""
        try:
            agent = self._get_agent()
            interrupted = False
            # async for 消费 Agent 的异步事件流，不阻塞事件循环中的其他任务。
            async for event in agent.stream(
                request.message,
                thread_id=self._request_thread_id(request),
                user_context=self._user_context(request),
            ):
                yield event
                interrupted = isinstance(event, HumanActionRequiredEvent)
            if not interrupted:
                yield DoneEvent()
        except AgentConfigurationError as error:
            yield ErrorEvent(code="AGENT_UNAVAILABLE", message=str(error))
        except Exception:
            # SSE 响应开始后不能再修改 HTTP 状态码，也不能暴露内部异常细节。
            yield ErrorEvent(code="STREAM_ERROR", message="流式聊天执行失败，请稍后重试")

    async def resume_chat(
        self, request: ChatResumeRequest
    ) -> AsyncIterator[AgentStreamEvent]:
        """恢复 checkpoint 中的 interrupt，不把 approval 追加成对话消息。"""
        try:
            interrupted = False
            async for event in self._get_agent().resume(
                request.thread_id, request.approval
            ):
                yield event
                interrupted = isinstance(event, HumanActionRequiredEvent)
            if not interrupted:
                yield DoneEvent()
        except AgentConfigurationError as error:
            yield ErrorEvent(code="AGENT_UNAVAILABLE", message=str(error))
        except Exception:
            yield ErrorEvent(code="RESUME_ERROR", message="恢复执行失败，请稍后重试")

    @staticmethod
    def _user_context(request: ChatRequest) -> UserContext:
        # Demo 信任请求中的模拟身份；生产入口应在这里改为验证后的 SSO/JWT claims。
        return {
            "user_id": request.resolved_user_id,
            "username": request.resolved_username,
            "roles": request.resolved_roles,
        }

    @staticmethod
    def _request_thread_id(request: ChatRequest) -> str:
        if request.session_id is not None:
            return build_thread_id(request.resolved_user_id, request.session_id)
        return request.thread_id

    async def start(self) -> None:
        """创建 SQLite Checkpointer；测试可注入内存或临时实现。"""
        if self._checkpointer is not None:
            return
        path = self._settings.checkpoint_db_path
        path.parent.mkdir(parents=True, exist_ok=True)
        context = AsyncSqliteSaver.from_conn_string(str(path))
        checkpointer = await context.__aenter__()
        try:
            await checkpointer.setup()
        except BaseException:
            await context.__aexit__(None, None, None)
            raise
        self._checkpointer_context = context
        self._checkpointer = checkpointer

    async def close(self) -> None:
        """应用关闭时释放由 Client 持有的 HTTP 连接池。"""
        if self._client is not None:
            await self._client.close()
        if self._embedding_provider is not None:
            await self._embedding_provider.close()
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
            self._checkpointer_context = None
            self._checkpointer = None

    def _get_agent(self) -> RequirementAgent:
        """惰性创建：/health 不需要模型 Key 或 Java 后端即可工作。"""
        if self._agent is None:
            if self._checkpointer is None:
                raise RuntimeError("ChatService.start() must be called before chat")
            self._client = RequirementClient(self._settings)
            requirement_tools = RequirementTools(self._client)
            retriever: KnowledgeRetriever | None = None
            if self._settings.siliconflow_api_key is not None:
                self._embedding_provider = SiliconFlowEmbeddingProvider(
                    self._settings.siliconflow_api_key,
                    str(self._settings.siliconflow_base_url),
                    self._settings.siliconflow_embedding_model,
                )
                vector_store = ChromaVectorStore(
                    self._settings.chroma_persist_directory,
                    self._settings.chroma_collection_name,
                )
                retriever = KnowledgeRetriever(self._embedding_provider, vector_store)
            knowledge_tools = KnowledgeTools(retriever)
            self._agent = self._agent_factory(
                self._settings,
                requirement_tools,
                knowledge_tools,
                self._checkpointer,
            )
        return self._agent
