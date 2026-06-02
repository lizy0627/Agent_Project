"""Compatibility re-export for legacy backend.app.main imports.

The canonical FastAPI application lives in app.main. Keep this module thin:
new runtime logic should be added to app/main.py instead.
"""

from app.main import app, create_app, frontend_page, open_browser

__all__ = ["app", "create_app", "frontend_page", "open_browser"]
