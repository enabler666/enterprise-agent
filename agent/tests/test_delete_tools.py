import asyncio

from app.agent.state import UserContext
from app.tools.delete_tools import DeleteAllowed, DeleteDenied, DeleteExecuted, DeleteTools


def context(user_id: str, *roles: str) -> UserContext:
    return {"user_id": user_id, "username": user_id, "roles": list(roles)}


def test_delete_prepare_returns_structured_permission_results() -> None:
    tools = DeleteTools()

    async def run() -> tuple[DeleteDenied | DeleteAllowed, DeleteDenied | DeleteAllowed]:
        denied = await tools.delete_prepare(
            {"document_id": "DOC001"}, context("user_A", "employee")
        )
        allowed = await tools.delete_prepare(
            {"document_id": "DOC001"}, context("user_B", "employee")
        )
        return denied, allowed

    denied, allowed = asyncio.run(run())

    assert isinstance(denied, DeleteDenied)
    assert denied.model_dump() == {
        "allowed": False,
        "error_code": "NO_PERMISSION",
        "reason": "该单据属于其他用户",
        "owner_id": "user_B",
    }
    assert isinstance(allowed, DeleteAllowed)
    assert allowed.model_dump() == {
        "allowed": True,
        "need_confirmation": True,
        "document_id": "DOC001",
        "risk": "HIGH",
    }


def test_delete_execute_rechecks_permission_instead_of_trusting_prepare() -> None:
    tools = DeleteTools()

    async def run() -> tuple[DeleteDenied | DeleteExecuted, DeleteAllowed | DeleteDenied]:
        denied = await tools.delete_execute("DOC001", context("user_A", "employee"))
        still_exists = await tools.delete_prepare(
            {"document_id": "DOC001"}, context("user_B", "employee")
        )
        return denied, still_exists

    denied, still_exists = asyncio.run(run())

    assert isinstance(denied, DeleteDenied)
    assert denied.error_code == "NO_PERMISSION"
    assert isinstance(still_exists, DeleteAllowed)


def test_delete_execute_removes_document_after_second_authorization() -> None:
    tools = DeleteTools()

    async def run() -> tuple[DeleteExecuted | DeleteDenied, DeleteAllowed | DeleteDenied]:
        executed = await tools.delete_execute(
            "DOC001", context("user_A", "admin")
        )
        missing = await tools.delete_prepare(
            {"document_id": "DOC001"}, context("user_B", "employee")
        )
        return executed, missing

    executed, missing = asyncio.run(run())

    assert isinstance(executed, DeleteExecuted)
    assert executed.document_id == "DOC001"
    assert isinstance(missing, DeleteDenied)
    assert missing.error_code == "DOCUMENT_NOT_FOUND"


def test_delete_prepare_rejects_invalid_document_id() -> None:
    result = asyncio.run(
        DeleteTools().delete_prepare(
            {"document_id": "../DOC001"}, context("user_B", "employee")
        )
    )

    assert isinstance(result, DeleteDenied)
    assert result.error_code == "INVALID_ARGUMENT"
