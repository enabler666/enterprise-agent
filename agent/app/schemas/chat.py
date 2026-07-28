"""FastAPI 聊天、人工确认接口的请求与响应模型。"""

from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from app.schemas.requirement import JavaApiModel


class ChatUser(JavaApiModel):
    """Demo 由接口模拟注入用户；生产环境应忽略客户端身份并读取 SSO/JWT。"""

    id: str = Field(min_length=1, max_length=128)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    roles: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("id", "username")
    @classmethod
    def strip_user_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, roles: list[str]) -> list[str]:
        normalized = [role.strip() for role in roles if role.strip()]
        return list(dict.fromkeys(normalized))


class ChatRequest(JavaApiModel):
    """兼容原 userId/sessionId，并支持 HITL Demo 的嵌套 user 输入。"""

    user: ChatUser | None = None
    user_id: str | None = Field(default=None, min_length=1, max_length=128)
    session_id: str | None = Field(default=None, min_length=1, max_length=128)
    thread_id: str = Field(
        default_factory=lambda: f"chat-{uuid4()}",
        min_length=1,
        max_length=128,
    )
    message: str = Field(min_length=1, max_length=4_000)

    @field_validator("user_id", "session_id", "thread_id", "message")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value

    @model_validator(mode="after")
    def require_user(self) -> ChatRequest:
        if self.user is None and self.user_id is None:
            raise ValueError("必须提供 user 或 userId")
        return self

    @property
    def resolved_user_id(self) -> str:
        return self.user.id if self.user is not None else str(self.user_id)

    @property
    def resolved_username(self) -> str:
        if self.user is not None and self.user.username:
            return self.user.username
        return self.resolved_user_id

    @property
    def resolved_roles(self) -> list[str]:
        return list(self.user.roles) if self.user is not None else []


class ChatResumeRequest(JavaApiModel):
    thread_id: str = Field(min_length=1, max_length=128)
    approval: bool

    @field_validator("thread_id")
    @classmethod
    def strip_thread_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("不能为空")
        return value


class ChatResponse(JavaApiModel):
    answer: str
    user_id: str
    session_id: str
