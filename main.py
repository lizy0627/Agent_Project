from pathlib import Path
from threading import Timer
import webbrowser

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.core.config import Settings, get_settings
from app.schemas import ChatRequest, ChatResponse
from app.services.dashscope_agent import DashScopeAgent


# 项目根目录，用于定位 frontend 静态文件目录。
BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"

# 本地开发服务地址，PyCharm 直接运行 main.py 时会自动打开这个页面。
HOST = "127.0.0.1"
PORT = 8000
FRONTEND_URL = f"http://{HOST}:{PORT}/ui"

app = FastAPI(
    title="DashScope Minimal Agent",
    description="基于 FastAPI 和 DashScope API 的最小聊天 Agent 示例。",
    version="0.1.0",
)

# 开发环境 CORS 配置：
# 允许浏览器页面从本地文件、PyCharm 预览或其他本地端口调用后端接口。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 将 frontend 目录挂载为静态资源目录，浏览器可以访问 CSS 和 JavaScript 文件。
app.mount(
    "/frontend",
    StaticFiles(directory=FRONTEND_DIR),
    name="frontend",
)


def get_agent(settings: Settings = Depends(get_settings)) -> DashScopeAgent:
    """创建 Agent 实例，并通过 Depends 注入到接口中。"""

    return DashScopeAgent(settings)


@app.get("/")
def health_check() -> dict[str, str]:
    """健康检查接口，用于确认服务已经启动。"""

    return {"status": "ok", "message": "DashScope Agent is running"}


@app.get("/ui")
def frontend_page() -> FileResponse:
    """前端聊天页面入口。"""

    # 返回 frontend/index.html，让用户通过后端地址直接使用聊天页面。
    return FileResponse(FRONTEND_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    agent: DashScopeAgent = Depends(get_agent),
) -> ChatResponse:
    """基础聊天接口：接收用户消息，返回 Agent 回复。"""

    # 将请求交给 Agent，由 Agent 负责组织上下文并调用模型。
    reply = agent.chat(
        message=request.message,
        system_prompt=request.system_prompt,
    )

    return ChatResponse(reply=reply, model=agent.model)


def open_browser() -> None:
    """延迟打开浏览器，确保 uvicorn 服务已经启动。"""

    webbrowser.open(FRONTEND_URL)


if __name__ == "__main__":
    # PyCharm 直接运行 main.py 时，会先启动一个定时器打开浏览器。
    # 延迟 1 秒是为了给 uvicorn 留出启动监听端口的时间。
    Timer(1.0, open_browser).start()

    # 启动 FastAPI 服务；在 PyCharm 中停止运行按钮即可关闭服务。
    uvicorn.run(app, host=HOST, port=PORT)
