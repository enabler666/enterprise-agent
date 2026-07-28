"""LangGraph 状态定义。"""

from typing import Annotated, Literal

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class UserContext(TypedDict):
    """由聊天入口注入的模拟登录用户；生产环境应由可信 SSO/JWT 构造。"""

    user_id: str
    username: str
    roles: list[str]


class PendingAction(TypedDict):
    """等待用户处理的高风险业务动作，不包含任何前端 UI 指令。"""

    action_type: Literal["DELETE_DOCUMENT"]
    target_id: str
    description: str


class RequirementAgentState(TypedDict):
    """图中各节点共享的状态。

``Annotated`` 将 ``add_messages`` 注册为 reducer；节点返回的新消息会追加到历史中，
Checkpointer 按 thread_id 恢复该字段。tool_rounds 只控制单次用户轮次，调用入口每轮重置。
"""

    messages: Annotated[list[AnyMessage], add_messages]
    tool_rounds: int
    # 身份进入 State 后可随 checkpoint 一起暂停和恢复；Agent 不需要在对话中询问账号。
    user_context: UserContext
    pending_action: PendingAction | None
    action_approved: bool | None
