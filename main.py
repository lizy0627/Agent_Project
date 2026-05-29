"""Compatibility entry point for the backend.app FastAPI application."""

from backend.app.main import app, create_app, frontend_page, open_browser
from backend.app.core.config import HOST, PORT, get_settings


if __name__ == "__main__":
    from threading import Timer

    import uvicorn

    settings = get_settings()
    if settings.auto_open_browser:
        Timer(1.0, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT)
