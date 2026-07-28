# 开发迭代记录

本文是项目开发路径和迭代状态的唯一记录。阶段按开发顺序持续追加，既记录每次迭代增加的功能，也标明接下来正在开发什么。

## 追加规则

- 新阶段只能追加在文件末尾，不重排或覆盖既有阶段。
- 当维护者明确表示“接下来开发某项能力”时，Agent 自动追加下一个阶段，写明阶段标题、`状态：进行中` 和本阶段目标。
- 开发过程中只更新当前阶段，不提前添加后续阶段。
- 阶段实现完成后，将计划性描述替换为实际完成内容，并标记为“待验收”。
- 维护者确认验证结果后，将状态改为“已完成”，记录必要的验证结果，然后停止并等待下一阶段指令。
- 每个阶段只记录功能、重要技术能力和验证结论，不复制接口详情、调试过程或文件清单。

## 阶段 1：Monorepo 项目骨架

状态：已完成

- 建立 `backend/`、`agent/`、`docs/` 和 Docker 目录结构。
- 初始化 Java 25 + Spring Boot 与 Python 3.14 + FastAPI 工程。
- 为 Java 后端和 Python Agent 增加健康检查。
- 建立基础测试与本地开发配置。

## 阶段 2：需求只读查询

状态：已完成

- 建立需求领域模型、状态枚举和 Repository 抽象。
- 增加内存 Repository 与固定演示数据。
- 提供需求详情、组合分页检索和当前进度三个 Java API。
- 增加统一响应、traceId、参数校验和全局异常处理。

## 阶段 3：MySQL 数据模式

状态：已完成

- 增加 MyBatis-Plus Repository，实现数据库过滤和分页。
- 增加 `mysql` Spring Profile，并保持 Controller、Service 接口不变。
- 使用 Flyway 创建需求表并初始化演示数据。
- 增加 Docker Compose MySQL 8.4 配置和 Testcontainers 集成测试。

## 阶段 4：Java 后端 Client

状态：已完成

- 建立 Python 配置与需求相关 Pydantic Schema。
- 使用异步 `httpx` 封装三个 Java 需求查询 API。
- 支持依赖注入与 `MockTransport`，避免测试访问真实 Java 服务。
- 支持 Java camelCase 与 Python snake_case 字段转换。

## 阶段 5：需求查询工具

状态：已完成

- 在 `RequirementClient` 之上增加详情、组合检索和进度查询工具。
- 使用 Pydantic 校验工具输入。
- 统一成功、无结果和失败三类工具执行结果。
- 对后端连接、协议和业务错误进行安全转换，不暴露内部细节。

## 阶段 6：DeepSeek 与 LangGraph Agent

状态：已完成

- 接入 OpenAI-compatible DeepSeek ChatModel。
- 使用 LangGraph 编排模型判断、工具调用和最终回答。
- 本阶段注册三个只读需求查询工具，并限制最多连续三轮工具调用；阶段 11 接入知识检索后，当前总数为四个 Tool。
- 增加基础多轮消息上下文和缺少 API Key 时的明确错误。
- 使用 Fake ChatModel 测试 Agent 流程，不调用真实 DeepSeek。

## 阶段 7：聊天接口与端到端联调

状态：已完成

- 新增 FastAPI `POST /chat` 接口，接收用户、会话和自然语言消息。
- 新增进程内会话上下文，支持基础多轮对话。
- 打通 FastAPI → LangGraph Agent → 查询工具 → Java API 的完整链路。
- 增加聊天接口、ChatService 和端到端 mock 测试。
- 补充本地启动、联调示例和常见错误说明。


## 阶段 8：SSE 流式聊天

状态：已完成

- 保留现有 `POST /chat`，新增 `POST /chat/stream` SSE 接口。
- 使用 LangGraph `messages + updates` 流式模式增量返回 DeepSeek 最终回答。
- 增加 `status`、`tool`、`message`、`error`、`done` 五种安全业务事件，隔离 LangGraph 原始事件及模型内部信息。
- 流正常完成后保存会话历史，中途断开或异常时不保存残缺轮次。
- 增加 SSE 路由、事件格式、流式会话保存测试与本地 curl 验证说明。

## 阶段 9：Markdown 业务文档加载与文本切分

状态：已完成

- 已实现从知识库目录稳定加载非空 Markdown 业务文档，统一文档模型并保留相对来源路径。
- 已按 Markdown 标题、自然段和中文句末边界切分文档，生成稳定且可追溯的文本块。
- 已提供独立预览命令，并以临时测试文档覆盖加载、顺序、标题、切分、来源和稳定标识。
- 本阶段不实现向量检索、Agent 接入或 FastAPI 接口。

## 阶段 10：知识块向量化与本地相似度检索

状态：已完成

- 已增加独立 Embedding Provider，并接入硅基流动批量 Embedding API 及完整异常处理。
- 已使用本地持久化 Chroma 保存向量、正文与来源元数据，采用完整重建策略清理旧索引。
- 已提供职责分离的索引构建、相似度检索能力和独立预览命令。
- 已校验索引与查询使用相同的 Embedding 模型，并增加隔离的本地向量存储与检索测试。
- 本阶段只验证检索能力，不接入 Agent、不生成最终回答、不修改 Java 后端。

## 阶段 11：知识库检索 Tool 与 Agent 接入

状态：已完成

- 已将现有 `KnowledgeRetriever` 封装为 `search_knowledge` Tool，并接入当前 LangGraph 的模型绑定与工具分发流程。
- 已按应用生命周期注入 Embedding Provider、Chroma VectorStore 和 Retriever，服务关闭时释放 HTTP 连接，且不会自动构建索引。
- 已补充知识回答约束、来源引用规则、安全错误结果和“企业知识库检索”SSE 状态展示。
- 已使用 Fake Model、Fake Retriever 和临时 Chroma 增加隔离测试，覆盖 Tool 分发、来源引用、无结果拒答和索引模型校验。
- 本阶段未修改 Java 后端，未组合结构化业务查询与知识库检索。

## 阶段 12：LangGraph 持久化线程状态

状态：已完成

- 已使用异步 SQLite Checkpointer 替换自定义 InMemorySessionStore，实现线程级短期记忆与服务重启后的 State 恢复，并由应用 lifespan 管理连接资源。
- 普通聊天与 SSE 流式聊天共用由用户和会话生成的稳定 thread_id，只提交本轮消息且重置 Tool 轮次，由 Checkpointer 作为唯一线程级状态来源。
- 业务数据库保存需求、工单等业务事实；Checkpointer 保存 thread 范围内的 Graph State 和执行快照；模型上下文由 Graph 节点从 State 中选择并组装，本阶段暂不裁剪。
- 已补充线程上下文、用户与会话隔离、消息去重、Tool 配对与轮次重置、SQLite 资源重建恢复、普通与 SSE 共用线程以及异常和中断状态测试，等待维护者执行 Python 依赖锁定与验证。
- 本阶段不实现 Human-in-the-loop、长期记忆、消息摘要或裁剪等后续能力。

## 阶段 13：高风险删除人工确认 Demo

状态：待验收

- 已扩展 LangGraph State，由聊天入口注入模拟用户身份，并持久化待确认删除动作。
- 已增加结构化删除预检查与执行 Tool，以内存单据和执行阶段重复权限校验模拟生产边界。
- 已使用 LangGraph interrupt、现有 Checkpointer 和相同 thread_id 实现暂停、确认或拒绝后的恢复。
- 已增加 `HUMAN_ACTION_REQUIRED` SSE 事件与聊天恢复接口，并保留原流式路径兼容别名。
- 已补充删除权限、参数、执行、checkpoint、恢复和 SSE 接口测试，等待维护者执行 Python 验证。
