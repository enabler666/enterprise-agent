import asyncio
from typing import Any, cast

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import InMemorySaver

from app.agent.events import HumanActionRequiredEvent, ToolEvent
from app.agent.graph import RequirementAgent
from app.agent.state import UserContext
from app.tools.delete_tools import DeleteDenied, DeleteTools
from app.tools.knowledge_tools import KnowledgeTools
from app.tools.requirement_tools import RequirementTools


class DeleteModel:
    def __init__(self) -> None:
        self.responses = [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "delete_prepare",
                        "args": {"document_id": "DOC001"},
                        "id": "delete-call-1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="单据 DOC001 已删除。"),
        ]

    async def ainvoke(self, _: list[BaseMessage]) -> BaseMessage:
        return self.responses.pop(0)


class UnusedBackend:
    async def get_requirement_by_no(self, *_: Any, **__: Any) -> Any:
        raise AssertionError

    async def search_requirements(self, *_: Any, **__: Any) -> Any:
        raise AssertionError

    async def get_requirement_progress(self, *_: Any, **__: Any) -> Any:
        raise AssertionError


def test_delete_interrupt_is_checkpointed_and_resumed_with_same_thread() -> None:
    delete_tools = DeleteTools()
    agent = RequirementAgent(
        cast(Runnable[Any, BaseMessage], DeleteModel()),
        RequirementTools(UnusedBackend()),
        KnowledgeTools(None),
        InMemorySaver(),
        delete_tools,
    )
    user_context: UserContext = {
        "user_id": "user_B",
        "username": "Bob",
        "roles": ["employee"],
    }

    async def run() -> tuple[list[object], dict[str, Any], list[object], DeleteDenied]:
        before_events = [
            event
            async for event in agent.stream(
                "删除单据 DOC001", "delete-thread", user_context
            )
        ]
        interrupted_state = dict((await agent.get_state("delete-thread")).values)
        after_events = [
            event async for event in agent.resume("delete-thread", approval=True)
        ]
        prepare_after_delete = await delete_tools.delete_prepare(
            {"document_id": "DOC001"}, user_context
        )
        assert isinstance(prepare_after_delete, DeleteDenied)
        return before_events, interrupted_state, after_events, prepare_after_delete

    before, interrupted_state, after, prepare_after_delete = asyncio.run(run())

    human_event = next(
        event for event in before if isinstance(event, HumanActionRequiredEvent)
    )
    assert human_event.thread_id == "delete-thread"
    assert human_event.action_type == "CONFIRM_DELETE"
    assert human_event.payload == {
        "document_id": "DOC001",
        "description": "删除采购单DOC001",
    }
    assert interrupted_state["user_context"] == user_context
    assert interrupted_state["pending_action"]["target_id"] == "DOC001"
    assert any(
        isinstance(event, ToolEvent)
        and event.tool == "单据删除执行"
        and event.status == "completed"
        for event in after
    )
    assert prepare_after_delete.error_code == "DOCUMENT_NOT_FOUND"
