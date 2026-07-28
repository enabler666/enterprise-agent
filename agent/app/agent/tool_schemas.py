"""暴露给模型的只读工具 JSON Schema。"""

from typing import Any


def requirement_tool_schemas() -> list[dict[str, Any]]:
    """描述模型可调用的需求数据与知识库工具，不包含实现细节。"""
    requirement_no = {
        "type": "object",
        "properties": {
            "requirement_no": {"type": "string", "description": "需求编号，例如 XQ202607001"}
        },
        "required": ["requirement_no"],
        "additionalProperties": False,
    }
    return [
        {
            "type": "function",
            "function": {
                "name": "get_requirement_by_no",
                "description": "根据明确的需求编号查询需求详情",
                "parameters": requirement_no,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_requirements",
                "description": "按标题、申请人、部门、状态、创建时间等条件组合查询需求",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "requirement_no": {"type": "string"},
                        "title": {"type": "string"},
                        "applicant_id": {"type": "string"},
                        "applicant_name": {"type": "string"},
                        "department": {"type": "string"},
                        "status": {
                            "type": "string",
                            "enum": [
                                "DRAFT", "PENDING_APPROVAL", "APPROVED", "REJECTED",
                                "EXECUTING", "COMPLETED", "CANCELLED"
                            ],
                        },
                        "created_from": {"type": "string", "format": "date-time"},
                        "created_to": {"type": "string", "format": "date-time"},
                        "page": {"type": "integer", "minimum": 0, "default": 0},
                        "size": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
                    },
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_requirement_progress",
                "description": "根据需求编号查询当前状态、处理节点和预计完成日期",
                "parameters": requirement_no,
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_knowledge",
                "description": "根据用户问题检索企业需求管理相关业务规则、操作说明和流程说明",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 2000,
                            "description": "需要查询知识库的完整业务问题",
                        }
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_prepare",
                "description": "删除单据前检查单据是否存在、当前用户是否有权限以及风险级别",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "明确的单据编号，例如 DOC001",
                        }
                    },
                    "required": ["document_id"],
                    "additionalProperties": False,
                },
            },
        },
    ]
