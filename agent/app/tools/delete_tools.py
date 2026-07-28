"""高风险删除 Demo Tool；内存数据仅用于演示生产权限边界。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agent.state import UserContext


class DeletePrepareInput(BaseModel):
    document_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

    @field_validator("document_id", mode="before")
    @classmethod
    def normalize_document_id(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class DeleteAllowed(BaseModel):
    allowed: Literal[True] = True
    need_confirmation: Literal[True] = True
    document_id: str
    risk: Literal["HIGH"] = "HIGH"


class DeleteDenied(BaseModel):
    allowed: Literal[False] = False
    error_code: str
    reason: str
    owner_id: str | None = None


class DeleteExecuted(BaseModel):
    success: Literal[True] = True
    document_id: str
    message: str = "单据已删除"


DeletePrepareResult = DeleteAllowed | DeleteDenied
DeleteExecuteResult = DeleteExecuted | DeleteDenied


class DeleteTools:
    """用内存 Map 模拟受保护业务后端。

    State 中的身份用于跨 interrupt 恢复上下文，但它不是权限结论。prepare 和 execute
    都会依据当前单据事实重新校验，模拟生产环境中 Tool/后端拥有最终授权责任。
    """

    def __init__(self, documents: dict[str, dict[str, str]] | None = None) -> None:
        self._documents = documents if documents is not None else {
            "DOC001": {"owner": "user_B"}
        }

    async def delete_prepare(
        self, payload: object, user_context: UserContext
    ) -> DeletePrepareResult:
        try:
            input_data = DeletePrepareInput.model_validate(payload)
        except ValidationError:
            return DeleteDenied(
                error_code="INVALID_ARGUMENT",
                reason="单据编号不合法",
            )
        return self._authorize(input_data.document_id, user_context)

    async def delete_execute(
        self, document_id: str, user_context: UserContext
    ) -> DeleteExecuteResult:
        # 恢复后的 State 可能过时或被错误构造，执行阶段必须重新读取业务事实并鉴权。
        authorization = self._authorize(document_id, user_context)
        if not authorization.allowed:
            return authorization
        del self._documents[document_id]
        return DeleteExecuted(document_id=document_id)

    def _authorize(
        self, document_id: str, user_context: UserContext
    ) -> DeletePrepareResult:
        document = self._documents.get(document_id)
        if document is None:
            return DeleteDenied(
                error_code="DOCUMENT_NOT_FOUND",
                reason="单据不存在或已删除",
            )
        owner_id = document["owner"]
        roles = set(user_context["roles"])
        if user_context["user_id"] != owner_id and "admin" not in roles:
            return DeleteDenied(
                error_code="NO_PERMISSION",
                reason="该单据属于其他用户",
                owner_id=owner_id,
            )
        return DeleteAllowed(document_id=document_id)
