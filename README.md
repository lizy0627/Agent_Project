# DashScope Agent Playground

一个基于 **FastAPI + DashScope OpenAI 兼容接口** 构建的轻量级 Agent 对话项目。项目包含后端对话接口、内存会话管理、规则式工具规划、工具调用层、联网搜索与网页读取能力，以及原生 HTML/CSS/JavaScript 实现的聊天前端。

这个项目适合作为简历项目或面试讲解案例：它不是复杂的通用 Agent 平台，而是围绕“用户输入 -> 工具判断 -> 工具执行 -> 模型总结 -> 前端展示”实现了一条可运行、可调试、便于扩展的基础 Agent 工作流。

## 项目架构

核心链路如下：

```text
用户输入
  -> FastAPI 接口
  -> ConversationStore
  -> Agent 规划
  -> ToolManager 工具调用
  -> DashScope 模型回答
  -> 前端展示
```

各模块职责：

- `frontend/`：原生前端页面，负责消息输入、流式响应展示、会话切换、本地会话缓存、Markdown 基础渲染和代码块复制。
- `app/api/chat.py`：FastAPI 路由层，提供健康检查、普通聊天和流式聊天接口，并组装请求上下文。
- `app/services/conversation_store.py`：会话存储层，默认使用内存存储，也可以通过配置切换为 SQLite 持久化存储。
- `app/services/dashscope_agent.py`：Agent 核心逻辑，负责判断是否需要工具、执行搜索工作流、拼接工具结果并调用 DashScope。
- `app/tools/`：本地工具层，包含时间、计算、文本总结、Tavily 搜索、网页读取和 MCP 工具包装。
- `app/tools/tool_manager.py`：统一管理工具注册、调用、日志和异常隔离。
- `app/mcp/`：MCP 配置、客户端、管理器和路由逻辑，用于接入外部 MCP Server。
- `app/core/`：配置、日志和错误处理。

## 技术栈

- **后端框架**：FastAPI
- **模型调用**：DashScope OpenAI-Compatible API，使用 `openai` Python SDK
- **配置管理**：Pydantic Settings + `.env`
- **前端实现**：原生 HTML、CSS、JavaScript
- **会话管理**：后端内存会话历史 + 前端 `localStorage`
- **工具系统**：自定义 `ToolManager`
- **联网能力**：Tavily Search API + 网页正文读取
- **MCP 接入**：支持通过 `app/mcp/servers.json` 配置 MCP Server
- **运行服务**：Uvicorn

## 功能说明

当前项目已实现：

- 普通对话接口：`POST /chat`
- 流式对话接口：`POST /chat/stream`
- FastAPI 自动接口文档：`GET /docs`
- 本地聊天页面：`GET /ui`
- 后端多轮上下文管理
- 前端多会话切换与本地保存
- 可选模型参数，支持请求时指定 DashScope 模型名称
- 可选系统提示词，支持请求时覆盖默认 system prompt
- 可选上下文轮数限制，避免一次请求携带过长历史
- 基础工具调用：
  - `get_current_time`：获取当前时间
  - `calculate`：执行数学计算
  - `summarize_text`：总结文本内容
  - `web_search`：通过 Tavily Search API 搜索网页
  - `web_reader`：读取网页正文，用于补充搜索材料
  - `mcp_tool`：调用已配置 MCP Server 暴露的工具
- 联网搜索工作流：默认搜索 3 条结果，并按需读取前 2 个网页正文用于模型总结
- 工具调用日志和耗时记录
- 工具失败时返回错误信息，不直接中断整个服务
- 统一异常处理，覆盖 API Key 缺失、鉴权失败、网络异常、模型超时等常见场景

## 项目结构

```text
.
├── app
│   ├── api
│   │   └── chat.py
│   ├── core
│   │   ├── config.py
│   │   ├── errors.py
│   │   └── logger.py
│   ├── mcp
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── manager.py
│   │   ├── router.py
│   │   ├── schema.py
│   │   └── servers.json
│   ├── schemas
│   │   └── chat.py
│   ├── services
│   │   ├── conversation_store.py
│   │   └── dashscope_agent.py
│   └── tools
│       ├── base.py
│       ├── calculator.py
│       ├── mcp_tool.py
│       ├── summarize_text.py
│       ├── time_tool.py
│       ├── tool_manager.py
│       ├── web_reader.py
│       └── web_search.py
├── frontend
│   ├── index.html
│   ├── main.js
│   └── style.css
├── scripts
│   ├── add_mcp_server.py
│   ├── list_mcp_tools.py
│   ├── test_mcp_connection.py
│   ├── test_mcp_server.py
│   └── test_mcp_tool_call.py
├── .env.example
├── main.py
├── requirements.txt
└── README.md
```

## 接口说明

### `GET /`

健康检查接口。

响应示例：

```json
{
  "status": "ok",
  "message": "DashScope Agent is running"
}
```

### `POST /chat`

普通聊天接口，一次性返回完整回复。

请求体字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `message` | string | 是 | 用户输入内容 |
| `system_prompt` | string | 否 | 自定义 system prompt，不传则使用默认中文助手提示词 |
| `model` | string | 否 | 指定 DashScope 模型，不传则使用 `.env` 中的默认模型 |
| `conversation_id` | string | 否 | 会话 ID，不传则后端自动生成 |
| `max_context_rounds` | number | 否 | 本次请求最多携带的历史轮数，范围为 0 到 30 |

请求示例：

```bash
curl -X POST "http://127.0.0.1:8000/chat" \
  -H "Content-Type: application/json" \
  -d "{\"message\":\"帮我计算 23 * 17 + 8 等于多少\"}"
```

响应示例：

```json
{
  "success": true,
  "reply": "23 * 17 + 8 的计算结果是 399。",
  "model": "qwen-plus",
  "conversation_id": "example-conversation-id",
  "used_tool": true,
  "tool_name": "calculate",
  "tool_status": "success",
  "tool_result": {
    "expression": "23 * 17 + 8",
    "value": 399
  },
  "tool_error": null,
  "tool_duration_ms": 1.23
}
```

### `POST /chat/stream`

流式聊天接口，使用 Server-Sent Events 返回状态、元数据、文本片段和完成事件。前端页面默认使用该接口，以获得逐字输出体验。

事件类型包括：

- `status`：工具或联网搜索阶段提示
- `metadata`：模型、会话和工具调用元信息
- `chunk`：模型生成的文本片段
- `done`：回复完成
- `error`：异常信息

### `GET /ui`

返回本地聊天前端页面。

### `GET /docs`

FastAPI 自动生成的接口文档页面。

## 本地运行

### 1. 创建并激活虚拟环境

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

Windows:

```bash
copy .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

编辑 `.env`：

```env
DASHSCOPE_API_KEY=your_dashscope_api_key_here
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
MODEL_TIMEOUT_SECONDS=30
CORS_ALLOW_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
CONVERSATION_STORE=memory
CONVERSATION_DB_PATH=data/conversations.db
AUTO_OPEN_BROWSER=true
TAVILY_API_KEY=your_tavily_api_key_here
WEB_SEARCH_PROVIDER=tavily
MCP_ENABLED=true
MCP_DEFAULT_SERVER=modelscope
MODELSCOPE_API_TOKEN=
MODELSCOPE_MCP_URL=http://127.0.0.1:8001/mcp
TOOL_TIMEOUT_SECONDS=20
```

主要配置说明：

- `DASHSCOPE_API_KEY`：DashScope API Key，必填，不要提交到 GitHub。
- `DASHSCOPE_BASE_URL`：DashScope OpenAI 兼容模式接口地址。
- `DASHSCOPE_MODEL`：默认模型名称，例如 `qwen-plus`。
- `MODEL_TIMEOUT_SECONDS`：模型请求超时时间，单位为秒；兼容旧配置名 `DASHSCOPE_TIMEOUT_SECONDS`。
- `CORS_ALLOW_ORIGINS`：允许跨域访问的来源，多个地址用英文逗号分隔；不配置时不会使用 `*`，默认只允许 `http://127.0.0.1:8000` 和 `http://localhost:8000`。
- `CONVERSATION_STORE`：会话存储方式，可选 `memory` 或 `sqlite`；默认 `memory`，保持原有内存会话行为。
- `CONVERSATION_DB_PATH`：SQLite 会话数据库路径，仅在 `CONVERSATION_STORE=sqlite` 时使用，默认 `data/conversations.db`。
- `AUTO_OPEN_BROWSER`：直接运行 `python main.py` 时是否自动打开浏览器，默认 `true`；设置为 `false` 时只启动服务。
- `TAVILY_API_KEY`：Tavily Search API Key，使用联网搜索时需要配置。
- `WEB_SEARCH_PROVIDER`：联网搜索提供商，当前代码使用 `tavily`。
- `MCP_ENABLED`：是否注册 MCP 工具。
- `MCP_DEFAULT_SERVER`：默认 MCP Server 名称。
- `MODELSCOPE_MCP_URL`：ModelScope MCP Server 地址。
- `TOOL_TIMEOUT_SECONDS`：工具相关请求超时时间，单位为秒；当前用于 MCP 连接和 MCP 工具调用，兼容旧配置名 `MCP_TIMEOUT_SECONDS`。

### 4. 启动服务

```bash
uvicorn main:app --reload
```

启动后访问：

- 后端健康检查：<http://127.0.0.1:8000/>
- API 文档：<http://127.0.0.1:8000/docs>
- 前端页面：<http://127.0.0.1:8000/ui>

也可以直接运行：

```bash
python main.py
```

## MCP 使用说明

项目默认在 `app/mcp/servers.json` 中配置了 `modelscope` 服务：

```json
{
  "modelscope": {
    "name": "ModelScope MCP Server",
    "transport": "http",
    "url": "http://127.0.0.1:8001/mcp",
    "enabled": true,
    "description": "用于搜索魔搭模型、数据集、创空间、论文和 MCP 服务"
  }
}
```

如果需要使用 MCP 工具，需要先在本地启动对应 MCP Server。例如 ModelScope MCP Server 可监听在 `http://127.0.0.1:8001/mcp`，再启动本项目。

测试 MCP 连接：

```bash
python scripts/test_mcp_connection.py
```

查看 MCP 工具：

```bash
python scripts/list_mcp_tools.py
```

测试一次工具调用：

```bash
python scripts/test_mcp_tool_call.py --server modelscope --tool search_models --arguments "{\"query\":\"Qwen\"}"
```

工具名称请以 `scripts/list_mcp_tools.py` 或 `scripts/test_mcp_server.py` 的输出为准。

## Agent 工具调用流程

当前项目使用轻量级规则进行工具规划，主要流程是：

1. FastAPI 接收用户消息，并通过 `ConversationStore` 读取历史上下文。
2. `DashScopeAgent` 根据最新用户输入判断是否需要工具。
3. 如果是时间、计算、总结、联网搜索或 ModelScope 相关问题，Agent 会生成对应工具调用计划。
4. `ToolManager` 执行工具，并记录日志、耗时、成功状态或错误信息。
5. Agent 将工具结果追加到模型上下文。
6. DashScope 生成最终中文回复。
7. 后端将回复和工具元信息返回给前端，前端负责展示。

需要说明的是，当前工具选择主要依赖规则和关键词判断，并非模型原生 Function Calling / Tool Calling。这种实现简单直接，便于展示 Agent 的基础工程链路，也方便后续替换为更标准的工具调用机制。

## 会话存储

项目默认使用内存版 `ConversationStore`，不需要额外配置，服务重启后历史会话会丢失。

如果希望在本地保留会话历史，可以在 `.env` 中切换为 SQLite：

```env
CONVERSATION_STORE=sqlite
CONVERSATION_DB_PATH=data/conversations.db
```

启用 SQLite 后，项目启动时会自动创建 `data` 目录和 `conversation_messages` 表。接口层仍然使用同一套 `get_messages`、`append_exchange` 调用方式，不需要修改聊天接口。

## 项目亮点

- **完整前后端闭环**：从浏览器输入、FastAPI 接口、Agent 处理到前端流式展示，形成可运行的最小闭环。
- **清晰的分层结构**：接口层、服务层、工具层、配置层和前端资源相互独立，方便讲解和维护。
- **可扩展工具系统**：通过 `ToolManager` 统一注册和调用工具，新增工具不需要改动接口层。
- **基础 Agent 工作流**：实现了任务判断、工具调用、工具结果注入模型上下文、最终回答生成的基本流程。
- **联网资料整理能力**：对于搜索类问题，支持先调用 Tavily，再按需读取网页正文，最后交给模型汇总。
- **MCP 扩展入口**：支持把外部 MCP Server 暴露的能力包装成项目内工具。
- **工程化细节**：包含配置管理、日志、异常封装、流式响应、请求参数校验和会话上下文控制。

## 当前限制

- 默认内存会话在服务重启后会丢失；如需本地持久化，可将 `CONVERSATION_STORE` 切换为 `sqlite`。
- 工具规划以规则和关键词为主，复杂意图识别能力有限。
- 联网搜索依赖 Tavily API Key，网页读取效果受目标网站结构和访问限制影响。
- MCP 工具需要外部 MCP Server 正常启动后才能使用。
- 当前项目未内置用户登录、多用户隔离、数据库持久化和完整自动化测试。

## 后续优化方向

- 接入模型原生 Function Calling / Tool Calling，替代当前规则式工具选择。
- 将会话历史迁移到 SQLite、PostgreSQL 或 Redis，实现持久化存储。
- 增加用户登录与多用户会话隔离。
- 为工具调用增加更完整的执行轨迹，例如 tool call id、参数脱敏、耗时统计和前端时间线展示。
- 补充单元测试和接口测试，覆盖工具执行、异常处理、流式输出和会话上下文。
- 增加 Dockerfile 和 Docker Compose，简化部署流程。
- 优化前端体验，例如会话搜索、消息重新生成、工具调用详情展开。
- 扩展更多实用工具，例如知识库检索、文件总结、数据库查询等。

## 简历描述参考

可以在简历中这样描述本项目：

```text
基于 FastAPI 和 DashScope OpenAI 兼容接口实现轻量级 Agent 对话应用，支持多轮会话、流式输出、规则式工具规划、Tavily 联网搜索、网页正文读取和 MCP 工具接入。项目通过 ConversationStore 管理上下文，通过 ToolManager 统一封装工具注册、调用、日志和异常隔离，并使用原生 HTML/CSS/JavaScript 实现可交互聊天前端。
```
