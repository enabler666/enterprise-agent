# Enterprise Support Agent Service

Python 3.14 Agent 服务通过 SSE 提供聊天，使用 DeepSeek + LangGraph 编排需求查询、知识检索和高风险删除确认 Demo。需求数据只通过异步 `httpx` 调用 Java API；知识问答通过 SiliconFlow Embedding 查询本地 Chroma 索引；删除仅操作进程内演示数据。

## 安装与配置

```bash
uv sync
```

配置全部来自环境变量：

```text
DEEPSEEK_API_KEY
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
BACKEND_BASE_URL=http://localhost:8080
BACKEND_TIMEOUT_SECONDS=10
SILICONFLOW_API_KEY
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_EMBEDDING_MODEL=BAAI/bge-m3
CHROMA_PERSIST_DIRECTORY=data/chroma
CHROMA_COLLECTION_NAME=requirement_knowledge
CHECKPOINT_DB_PATH=data/checkpoints.sqlite
```

Agent 不直接访问数据库。缺少 `DEEPSEEK_API_KEY` 时 `/health` 仍可用，SSE 流返回 `AGENT_UNAVAILABLE` 类型的 `error` 事件。

缺少 `SILICONFLOW_API_KEY` 时，三个需求查询 Tool 仍可工作；模型选择 `search_knowledge` 后会收到 `EMBEDDING_NOT_CONFIGURED` 安全错误。服务不会自动构建知识索引：索引不存在时返回 `KNOWLEDGE_INDEX_NOT_READY`，当前查询模型与索引模型不一致时返回 `EMBEDDING_MODEL_MISMATCH`。这些结果不会暴露密钥、底层堆栈或本地目录。

## 构建知识索引

业务知识位于仓库根目录 `knowledge/`。加载器递归读取 UTF-8 Markdown，切分器优先按 Markdown 标题和自然段切分，超长段落再按中文句末切分；默认目标长度约 700 字符、重叠约 100 字符。

配置 `SILICONFLOW_API_KEY` 后，在 `agent/` 目录完整重建索引：

```bash
uv run python -m app.rag.indexer
```

索引器会先删除同名 collection 再完整写入，因此重复构建不会累积重复 chunk，已删除文档也不会残留。Chroma 使用 `PersistentClient` 在本地持久化；相对的 `CHROMA_PERSIST_DIRECTORY` 始终以 `agent/` 为基准。

预览 Markdown 切分结果与向量检索结果：

```bash
uv run python -m app.rag.preview
uv run python -m app.rag.search_preview "一级统筹是不是必须经过？"
```

预览命令可以显示检索内部字段用于本地诊断；Agent 最终回答不会向用户输出向量、distance、chunk ID、片段序号或绝对路径。

## 启动服务

```bash
uv run uvicorn app.main:app --reload --port 8000
```

健康检查为 `GET http://localhost:8000/health`。需求查询还需启动 Java 后端；知识问答需要预先构建索引并保持查询与索引使用相同的 Embedding 模型。

## 发起聊天 `POST /chat`

入口允许用请求参数模拟用户身份；生产环境中同一信息应由服务端从 SSO/JWT 注入，不能信任客户端自报身份。`username` 和 `threadId` 可省略，省略 `threadId` 时接口会生成并在人工确认事件中返回：

```json
{
  "user": {
    "id": "user_B",
    "username": "Bob",
    "roles": ["employee"]
  },
  "threadId": "hitl-demo-001",
  "message": "删除单据 DOC001"
}
```

发起允许的删除请求：

```bash
curl -N -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"user":{"id":"user_B","username":"Bob","roles":["employee"]},"threadId":"hitl-demo-001","message":"删除单据 DOC001"}'
```

典型暂停事件：

```text
event: HUMAN_ACTION_REQUIRED
data: {"thread_id":"hitl-demo-001","action_type":"CONFIRM_DELETE","payload":{"document_id":"DOC001","description":"删除采购单DOC001"}}
```

`DOC001` 的演示 owner 是 `user_B`。使用 `user_A + employee` 会得到结构化的 `NO_PERMISSION` Tool 结果，不会进入人工确认；`admin` 角色也允许进入确认。

## 恢复执行 `POST /chat/resume`

确认删除时必须使用暂停事件返回的同一个 `thread_id`：

```bash
curl -N -X POST "http://localhost:8000/chat/resume" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{"threadId":"hitl-demo-001","approval":true}'
```

拒绝时将 `approval` 改为 `false`，Graph 会结束本次待处理动作且不会调用执行 Tool。公开事件如下：

| 事件 | 说明 |
| --- | --- |
| `status` | 请求已进入处理流程 |
| `tool` | 安全、概括的工具开始或完成状态 |
| `message` | 面向用户的最终回答文本增量 |
| `error` | 响应开始后的结构化错误，随后结束连接 |
| `done` | LangGraph 流正常完成 |
| `HUMAN_ACTION_REQUIRED` | Graph 已 checkpoint，等待客户端提交指定人工动作 |

`POST /chat/stream` 暂时保留为 `/chat` 的兼容别名；原同步返回接口迁移到 `POST /chat/sync`。SSE 路由不转发 LangGraph 原始事件，不输出 reasoning、系统提示词、Tool 参数或原始 Tool 结果。

## 会话边界

新请求可显式传 `threadId`，也可由接口生成；兼容输入 `userId + sessionId` 仍会生成稳定的 LangGraph `thread_id`。SQLite Checkpointer 保存消息、模拟用户上下文、待确认动作和 interrupt 快照，因此恢复必须使用相同 `thread_id`。默认文件为 `agent/data/checkpoints.sqlite`；SQLite 只适合本地单实例 Demo。

## 当前 Tool 与 RAG 边界

| Tool | 数据来源 |
| --- | --- |
| `get_requirement_by_no` | Java 需求详情 API |
| `search_requirements` | Java 组合条件分页 API |
| `get_requirement_progress` | Java 需求进度 API |
| `search_knowledge` | Chroma Markdown 知识索引，固定 TopK 3 |
| `delete_prepare` | 内存单据 Map，检查存在性、归属和风险 |
| `delete_execute` | 人工确认后由 Graph 调用，并再次检查权限 |

当前 RAG 只做向量 TopK 召回，不包含相似度阈值、Rerank、Hybrid Search、Query Rewrite 或自动评测。系统提示词暂不允许在同一轮组合结构化需求 Tool 与知识库 Tool。

## Windows 中文请求

PowerShell 直接将中文传给 `curl.exe` 时可能使用本地代码页。可以将中文写成 JSON Unicode 转义，或显式传入 UTF-8 字节：

```powershell
$body = @{
  userId = "demo-user"
  sessionId = "demo-session"
  message = "XQ202607002 目前进展怎么样？"
} | ConvertTo-Json -Compress

$bytes = [System.Text.Encoding]::UTF8.GetBytes($body)

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/chat" `
  -ContentType "application/json; charset=utf-8" `
  -Body $bytes
```

## 测试与静态检查

Python 环境及验证由维护者执行：

```bash
uv lock
uv run pytest
uv run ruff check .
uv run mypy app tests
```

测试使用 Fake Model、Fake Retriever、`httpx.MockTransport` 和临时 Chroma，不访问真实 Java、DeepSeek 或 SiliconFlow 服务。完整跨模块说明见 [当前调用链](../docs/current-flow.md)，Java 接口契约见 [需求查询 API](../docs/requirement-api.md)。
