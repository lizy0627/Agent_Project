# DashScope Minimal Agent

这是一个基于 Python、FastAPI 和 DashScope API 的最小 Agent 项目，支持基础聊天，并通过环境变量读取 API Key。

## 1. 安装依赖

原理：`requirements.txt` 记录项目运行需要的 Python 包，方便在新环境中一次性安装。

```bash
pip install -r requirements.txt
```

主要依赖：

- `fastapi`：提供 Web API 框架。
- `uvicorn`：作为 ASGI 服务运行 FastAPI。
- `openai`：通过 OpenAI 兼容模式调用 DashScope。
- `pydantic-settings`：从环境变量和 `.env` 文件读取配置。

## 2. 配置环境变量

原理：API Key 属于敏感信息，不应该硬编码在代码中；项目启动时从环境变量或 `.env` 文件读取。

复制示例配置：

```bash
copy .env.example .env
```

然后编辑 `.env`：

```env
DASHSCOPE_API_KEY=你的 DashScope API Key
DASHSCOPE_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-plus
```

## 3. 启动服务

原理：`main.py` 中已经写好了本地启动逻辑。你在 PyCharm 里直接运行 `main.py` 时，程序会启动 FastAPI 服务，并自动打开浏览器进入聊天页面。

推荐方式：在 PyCharm 中打开 `main.py`，点击运行按钮。

也可以在命令行运行：

```bash
python main.py
```

启动后会自动打开：

```text
http://127.0.0.1:8000/ui
```

备用方式：如果你更喜欢手动用 `uvicorn` 启动，也可以运行：

```bash
uvicorn main:app --reload
```

这种方式不会自动打开浏览器，需要手动访问：

- 健康检查：`http://127.0.0.1:8000/`
- 接口文档：`http://127.0.0.1:8000/docs`
- 前端页面：`http://127.0.0.1:8000/ui`

## 4. 打开前端页面聊天

原理：前端页面使用原生 HTML、CSS 和 JavaScript 编写；浏览器通过 `fetch` 请求后端 `/chat` 接口，后端再调用 DashScope 模型。

启动后端后，浏览器页面会自动打开。页面会请求：

```text
POST http://127.0.0.1:8000/chat
```

请求体格式：

```json
{
  "message": "你好，请用一句话介绍你自己"
}
```

响应体格式：

```json
{
  "reply": "你好，我是一个基于通义千问的中文 AI 助手。",
  "model": "qwen-plus"
}
```

说明：项目已在 `main.py` 中挂载 `frontend` 静态目录，并添加 `/ui` 页面入口，因此前端页面由 FastAPI 统一提供。

前端页面包含：

- 左侧侧边栏：`Agent_Project`、新建对话按钮、当前会话 ID。
- 右侧聊天区：用户消息靠右，Agent 消息靠左，并自动滚动到底部。
- 底部输入区：支持多行输入，`Enter` 发送，`Shift + Enter` 换行。
- 本地会话：前端会自动生成 `conversation_id` 并保存到 `localStorage`，为后续多轮对话扩展做准备。

## 5. 调用聊天接口

原理：客户端向 `/chat` 发送用户消息，FastAPI 校验请求体后交给 `DashScopeAgent`，Agent 组织 `system` 和 `user` 消息并调用 DashScope 模型。

```bash
curl -X POST "http://127.0.0.1:8000/chat" ^
  -H "Content-Type: application/json" ^
  -d "{\"message\":\"你好，请用一句话介绍你自己\"}"
```

响应示例：

```json
{
  "reply": "你好，我是一个基于通义千问的中文 AI 助手，可以帮你聊天、问答和处理文本任务。",
  "model": "qwen-plus"
}
```

## 6. 项目结构

原理：将配置、数据模型、业务服务和 Web 入口分开，后续扩展多轮对话、工具调用或数据库会更清晰。

```text
.
├── app
│   ├── core
│   │   └── config.py          # 配置读取：从环境变量或 .env 获取 DashScope 参数
│   ├── services
│   │   └── dashscope_agent.py # Agent 服务：组织消息并调用 DashScope API
│   ├── __init__.py
│   └── schemas.py             # 请求和响应模型
├── frontend
│   ├── index.html             # 前端页面结构
│   ├── main.js                # 前端交互逻辑：发送消息、调用后端、展示回复
│   └── style.css              # 前端页面样式
├── .env.example               # 环境变量示例
├── .gitignore                 # 忽略 .env、缓存和日志等本地文件
├── main.py                    # FastAPI 应用入口，PyCharm 运行后自动打开浏览器
├── README.md                  # 使用说明和原理解释
└── requirements.txt           # Python 依赖
```

## 7. 核心流程

1. 用户请求 `/chat`。
2. FastAPI 使用 `ChatRequest` 校验输入。
3. `get_settings()` 从环境变量读取 DashScope 配置。
4. `DashScopeAgent` 创建 OpenAI 兼容客户端。
5. Agent 把用户输入转换成模型消息列表。
6. DashScope 返回回答。
7. FastAPI 使用 `ChatResponse` 返回结构化 JSON。
8. 前端把 `reply` 显示为左侧 Agent 消息。
