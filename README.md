# DashScope Agent Playground

一个基于 **FastAPI + DashScope OpenAI 兼容接口** 构建的轻量级 Agent 项目，包含后端对话接口、本地多轮会话管理、基础工具调用能力，以及原生 HTML/CSS/JavaScript 实现的聊天界面。

项目适合作为 Agent 入门实践、简历项目展示或面试讲解案例：它不只是一个普通聊天机器人，还具备基础的“判断任务 -> 调用工具 -> 结合工具结果生成最终回答”的 Agent 工作流。

## 技术栈

- **后端框架**：FastAPI
- **模型调用**：DashScope OpenAI-Compatible API，使用 `openai` Python SDK
- **配置管理**：Pydantic Settings + `.env`
- **前端实现**：原生 HTML、CSS、JavaScript
- **会话管理**：后端内存会话历史 + 前端 `localStorage`
- **工具系统**：自定义 `ToolManager`，支持工具注册、调用、日志和异常隔离
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
```

说明：

- `DASHSCOPE_API_KEY`：DashScope API Key，请填写自己的 Key，不要提交到 GitHub
- `DASHSCOPE_BASE_URL`：DashScope OpenAI 兼容模式接口地址
- `DASHSCOPE_MODEL`：使用的模型名称，例如 `qwen-plus`
- `DASHSCOPE_TIMEOUT_SECONDS`：模型请求超时时间，单位为秒
- `TAVILY_API_KEY`：Tavily Search API Key，请填写自己的 Key，不要提交到 GitHub
- `WEB_SEARCH_PROVIDER`：联网搜索提供商，当前支持 `tavily`

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
