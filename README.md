# DashScope Agent Playground

一个基于 **FastAPI + DashScope OpenAI 兼容接口** 构建的轻量级 Agent 项目，包含后端对话接口、本地多轮会话管理、基础工具调用能力，以及原生 HTML/CSS/JavaScript 实现的聊天界面。

项目适合作为 Agent 入门实践、简历项目展示或面试讲解案例：它不只是一个普通聊天机器人，还具备基础的“判断任务 -> 调用工具 -> 结合工具结果生成最终回答”的 Agent 工作流。

## 技术栈

- **后端框架**：FastAPI
- **模型调用**：DashScope OpenAI-Compatible API，使用 `openai` Python SDK
- **配置管理**：Pydantic Settings + `.env`
- **前端实现**：原生 HTML、CSS、JavaScript
- **会话管理**：后端内存会话历史 + 前端 `localStorage`
- **工具系统**：自定义 `ToolManager`，支持本地工具和 MCP 工具注册、调用、日志和异常隔离
- **运行服务**：Uvicorn

## 功能列表

- 支持普通聊天接口：`POST /chat`
- 支持流式聊天接口：`POST /chat/stream`
- 支持 FastAPI 自动接口文档：`/docs`
- 支持本地前端页面：`/ui`
- 支持多轮对话上下文管理
- 支持多会话切换与前端本地保存
- 支持基础 Agent 工具调用：
  - `get_current_time`：获取当前时间
  - `calculate`：执行安全数学计算
  - `summarize_text`：总结文本内容
  - `web_search`：通过 Tavily Search API 进行联网搜索
  - `web_reader`：读取搜索结果网页正文，用于多来源综合总结
  - `mcp_tool`：调用已配置 MCP Server 暴露的工具
- 支持通过 `app/mcp/servers.json` 配置多个 MCP Server，默认包含 ModelScope MCP Server
- 联网搜索工作流默认搜索 3 条结果，并读取前 2 个网页正文用于最终总结
- 工具调用过程带日志，便于调试
- 工具失败不会导致服务崩溃，会将失败信息交给模型生成最终回复
- 统一异常处理，覆盖 API Key 缺失、鉴权失败、网络异常、模型超时等场景
- 前端支持 Markdown 基础渲染、代码块复制、加载状态、错误提示

## 项目结构

```text
.
├── app
│   ├── api
│   │   ├── __init__.py
│   │   └── chat.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── errors.py
│   │   └── logger.py
│   ├── mcp
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── config.py
│   │   ├── manager.py
│   │   ├── router.py
│   │   ├── schema.py
│   │   └── servers.json
│   ├── schemas
│   │   ├── __init__.py
│   │   └── chat.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── conversation_store.py
│   │   └── dashscope_agent.py
│   ├── tools
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── calculator.py
│   │   ├── mcp_tool.py
│   │   ├── summarize_text.py
│   │   ├── time_tool.py
│   │   ├── web_reader.py
│   │   ├── web_search.py
│   │   └── tool_manager.py
│   └── __init__.py
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
├── .gitignore
├── main.py
├── README.md
└── requirements.txt
```

## 本地运行

### 1. 克隆项目

```bash
git clone <your-repository-url>
cd <your-repository-name>
```

### 2. 创建虚拟环境

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

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

复制示例配置文件：

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
DASHSCOPE_TIMEOUT_SECONDS=30
TAVILY_API_KEY=your_tavily_api_key_here
WEB_SEARCH_PROVIDER=tavily
MCP_ENABLED=true
MCP_DEFAULT_SERVER=modelscope
MODELSCOPE_API_TOKEN=
MODELSCOPE_MCP_URL=http://127.0.0.1:8001/mcp
MCP_TIMEOUT_SECONDS=20
```

说明：

- `DASHSCOPE_API_KEY`：DashScope API Key，请填写自己的 Key，不要提交到 GitHub
- `DASHSCOPE_BASE_URL`：DashScope OpenAI 兼容模式接口地址
- `DASHSCOPE_MODEL`：使用的模型名称，例如 `qwen-plus`
- `DASHSCOPE_TIMEOUT_SECONDS`：模型请求超时时间，单位为秒
- `TAVILY_API_KEY`：Tavily Search API Key，请填写自己的 Key，不要提交到 GitHub
- `WEB_SEARCH_PROVIDER`：联网搜索提供商，当前支持 `tavily`
- `MCP_ENABLED`：是否启用 MCP 工具层
- `MCP_DEFAULT_SERVER`：默认 MCP Server，初始值为 `modelscope`
- `MODELSCOPE_API_TOKEN`：ModelScope 访问令牌，按你启动 ModelScope MCP Server 的方式配置
- `MODELSCOPE_MCP_URL`：ModelScope MCP Server 的 Streamable HTTP 地址
- `MCP_TIMEOUT_SECONDS`：MCP 连接和工具调用超时时间，单位为秒

### 5. 启动服务

```bash
uvicorn main:app --reload
```

启动后可以访问：

- 后端健康检查：<http://127.0.0.1:8000/>
- API 文档：<http://127.0.0.1:8000/docs>
- 前端页面：<http://127.0.0.1:8000/ui>

也可以直接运行：

```bash
python main.py
```

## 接口示例

### 普通聊天

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
  "tool_result": {
    "expression": "23 * 17 + 8",
    "value": 399
  }
}
```

### 流式聊天

前端页面默认调用 `/chat/stream`，后端通过 Server-Sent Events 持续返回模型生成内容，适合更自然的对话体验。

## Agent 工具调用流程

当前项目采用轻量级规则规划器完成基础工具选择：

1. 接收用户消息并读取会话上下文
2. 判断是否需要调用本地工具
3. 通过 `ToolManager` 执行工具
4. 将工具结果追加到模型上下文
5. 调用 DashScope 生成最终自然语言回复
6. 工具异常会被捕获并写入日志，不会中断整个服务

这种设计便于后续扩展更多工具，例如网页搜索、数据库查询、文件分析、代码执行沙箱等。

## MCP 工具接入

MCP（Model Context Protocol）是一套让 Agent 以统一协议连接外部工具和数据源的标准。接入 MCP 后，本项目可以在保留原有 `ToolManager` 的基础上，把外部 MCP Server 暴露的能力包装成一个普通工具 `mcp_tool`，继续沿用现有的工具调用、日志和异常隔离流程。

本项目适合接入 MCP 的原因：

- 已经有轻量级规则规划器，可以根据用户问题决定是否调用工具
- 已经有统一 `ToolManager`，MCP 只需要作为新工具层接入
- `/chat` 和 `/chat/stream` 都会把工具结果加入模型上下文，再由 DashScope 生成自然语言回复
- 未来可以继续加入 amap、filesystem、github、database、browser 等 MCP Server

默认 MCP 配置位于 `app/mcp/servers.json`：

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

`.env` 中可以覆盖 ModelScope MCP 地址：

```env
MCP_ENABLED=true
MCP_DEFAULT_SERVER=modelscope
MODELSCOPE_API_TOKEN=
MODELSCOPE_MCP_URL=http://127.0.0.1:8001/mcp
MCP_TIMEOUT_SECONDS=20
```

### 启动 ModelScope MCP Server

请先按 ModelScope MCP Server 官方文档在本地启动服务。官方示例支持 Streamable HTTP transport，可以用下面的方式把端口改成本项目默认的 `8001`：

```bash
export MODELSCOPE_API_TOKEN="your-modelscope-token"
uv run modelscope-mcp-server --transport http --port 8001
```

Windows PowerShell:

```powershell
$env:MODELSCOPE_API_TOKEN="your-modelscope-token"
uv run modelscope-mcp-server --transport http --port 8001
```

启动后确认它监听：

```text
http://127.0.0.1:8001/mcp
```

如果你的服务地址不同，修改 `.env` 中的 `MODELSCOPE_MCP_URL`，或修改 `app/mcp/servers.json` 中 `modelscope.url`。ModelScope 官方 README 中的默认 HTTP URL 是 `http://127.0.0.1:8000/mcp/`，本项目为了避免和 FastAPI 主服务冲突，默认使用 `8001`。

### 测试 MCP 连接

启动 ModelScope MCP Server 后，在项目根目录运行：

```bash
python scripts/test_mcp_connection.py
```

脚本会连接 `http://127.0.0.1:8001/mcp` 并打印工具列表。

测试一次真实工具调用：

```bash
python scripts/test_mcp_tool_call.py --server modelscope --tool search_models --arguments "{\"query\":\"Qwen\"}"
```

工具名请以 `python scripts/test_mcp_server.py --server modelscope` 或 `python scripts/list_mcp_tools.py` 输出为准。

### 在聊天页面使用

启动后端和 ModelScope MCP Server 后，打开 <http://127.0.0.1:8000/ui>，输入类似问题：

```text
搜索 Qwen3 相关模型
帮我查一下 ModelScope 上有哪些通义千问相关数据集
找几篇 Qwen 相关论文
```

当问题包含“魔搭、ModelScope、模型、数据集、dataset、创空间、论文、paper、MCP服务、Qwen、通义千问”等关键词时，Agent 会优先尝试调用 `modelscope` MCP Server。若 MCP 调用失败，回复会提示检查 MCP Server 是否启动、地址是否正确。

### 添加新的 MCP Server

在 `app/mcp/servers.json` 中添加新的服务配置即可，例如：

```json
{
  "github": {
    "name": "GitHub MCP Server",
    "transport": "http",
    "url": "http://127.0.0.1:8002/mcp",
    "enabled": true,
    "description": "用于查询 GitHub 仓库、Issue 和 Pull Request"
  }
}
```

新增后可以通过 `MCPManager.list_all_tools()` 查看所有工具，通过 `MCPManager.call_tool(server_name, tool_name, arguments)` 调用指定工具。聊天侧会先用 server 的 `keywords` 初筛，再根据工具名称、描述和 `input_schema` 自动选择工具，不需要为每个 MCP Server 修改 `dashscope_agent.py`。

## 如何接入新的魔搭社区 MCP 工具

1. 在魔搭社区找到需要接入的 MCP 工具。
2. 复制该 MCP 工具的启动命令，并尽量使用 Streamable HTTP transport。
3. 启动新的 MCP Server，例如监听 `http://127.0.0.1:8002/mcp`。
4. 将 server 信息加入 `app/mcp/servers.json`，或使用脚本添加：

```cmd
python scripts/add_mcp_server.py ^
  --id amap ^
  --name "Amap MCP Server" ^
  --url http://127.0.0.1:8002/mcp ^
  --keywords 地图,路线,天气,导航 ^
  --description "高德地图相关 MCP 工具"
```

5. 测试连接并查看工具：

```cmd
python scripts/test_mcp_server.py --server amap
python scripts/list_mcp_tools.py
```

6. 指定工具做一次真实调用：

```cmd
python scripts/test_mcp_tool_call.py ^
  --server modelscope ^
  --tool search_models ^
  --arguments "{\"query\":\"Qwen\"}"
```

7. 启动 Agent 项目，在前端聊天页面测试自然语言提问。

`servers.json` 支持多个 MCP Server。推荐格式：

```json
{
  "modelscope": {
    "name": "ModelScope MCP Server",
    "transport": "http",
    "url": "http://127.0.0.1:8001/mcp",
    "enabled": true,
    "keywords": ["魔搭", "ModelScope", "模型", "数据集", "论文", "创空间", "Qwen", "通义千问"],
    "description": "用于搜索魔搭模型、数据集、论文、创空间和 MCP 服务",
    "timeout_seconds": 20,
    "command": null,
    "args": [],
    "env": {
      "MODELSCOPE_API_TOKEN": "${MODELSCOPE_API_TOKEN}"
    },
    "headers": {},
    "category": "model-community"
  }
}
```

不要把 token 写死在代码或 JSON 明文里；需要密钥时放入 `.env`，再用 `${ENV_NAME}` 引用。

完整启动流程如下。

第一个 CMD，启动 ModelScope MCP Server：

```cmd
uvx modelscope-mcp-server --transport http --port 8001
```

第二个 CMD，启动 Agent 项目：

```cmd
cd /d D:\Agent
.venv\Scripts\activate
uvicorn main:app --reload
```

访问：

```text
http://127.0.0.1:8000/ui
```

## 界面截图

建议在 GitHub 仓库中新增 `docs/images/` 目录，并放入以下截图：

```text
docs/images/chat-home.png        # 聊天首页
docs/images/tool-call-demo.png   # 工具调用结果展示
docs/images/api-docs.png         # FastAPI 接口文档
```

README 中可以使用以下占位写法：

```md
![聊天首页](docs/images/chat-home.png)
![工具调用演示](docs/images/tool-call-demo.png)
![API 文档](docs/images/api-docs.png)
```

## 后续优化方向

- 接入模型原生 Function Calling / Tool Calling，替代当前规则式工具选择
- 为工具调用增加更完整的执行轨迹，例如 tool call id、耗时、参数脱敏
- 将会话历史从内存迁移到 SQLite、PostgreSQL 或 Redis
- 增加用户登录与多用户会话隔离
- 增加单元测试和接口测试，覆盖工具执行、异常处理和流式输出
- 增加 Dockerfile 与 Docker Compose，提升部署便利性
- 优化前端交互，例如工具调用时间线、会话搜索、消息重新生成
- 增加更多 Agent 工具，例如网页搜索、知识库检索、文件总结、代码解释

## 项目亮点

- 代码结构清晰，后端分为 `api`、`core`、`schemas`、`services`、`tools`
- 具备真实可运行的前后端闭环，而不是只停留在模型 API 调用示例
- 通过 `ToolManager` 抽象工具注册和调用，方便扩展更多 Agent 能力
- 具备基础工程化处理：配置管理、日志、异常封装、流式响应、多轮会话
- 适合在面试中讲解 Agent 的基本工作流、工程拆分思路和后续扩展路径
