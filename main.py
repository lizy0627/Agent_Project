"""Compatibility entry point for the backend.app FastAPI application."""

from backend.app.core.config import HOST, PORT, get_settings
from backend.app.main import app, create_app, open_browser

__all__ = ["app", "create_app", "open_browser"]


if __name__ == "__main__":
    from threading import Timer

    import uvicorn

    settings = get_settings()
    if settings.auto_open_browser:
        Timer(1.0, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT)
