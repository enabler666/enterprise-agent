"""Agent 流式业务事件；隔离 LangGraph 内部事件格式。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypeAlias, TypedDict


@dataclass(frozen=True)
class StatusEvent:
    type: Literal["status"] = "status"
    status: str = "processing"
    message: str = "正在处理请求"


@dataclass(frozen=True)
class ToolEvent:
    tool: str
    status: Literal["started", "completed"]
    message: str
    type: Literal["tool"] = "tool"


@dataclass(frozen=True)
class MessageEvent:
    content: str
    type: Literal["message"] = "message"


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    message: str
    type: Literal["error"] = "error"


@dataclass(frozen=True)
class DoneEvent:
    type: Literal["done"] = "done"


class HumanActionPayload(TypedDict):
    document_id: str
    description: str


@dataclass(frozen=True)
class HumanActionRequiredEvent:
    thread_id: str
    action_type: Literal["CONFIRM_DELETE"]
    payload: HumanActionPayload
    type: Literal["HUMAN_ACTION_REQUIRED"] = "HUMAN_ACTION_REQUIRED"


AgentStreamEvent: TypeAlias = (
    StatusEvent
    | ToolEvent
    | MessageEvent
    | ErrorEvent
    | DoneEvent
    | HumanActionRequiredEvent
)
