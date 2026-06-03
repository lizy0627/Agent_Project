"""Compatibility exports for legacy backend.app settings imports.

The canonical settings implementation lives in top-level app.config.settings.
"""

from app.config.settings import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    BASE_DIR,
    CORS_ALLOW_ORIGINS,
    DEFAULT_CORS_ALLOW_ORIGINS,
    FRONTEND_DIR,
    FRONTEND_URL,
    HOST,
    PORT,
    Settings,
    get_settings,
)

__all__ = [
    "APP_DESCRIPTION",
    "APP_TITLE",
    "APP_VERSION",
    "BASE_DIR",
    "CORS_ALLOW_ORIGINS",
    "DEFAULT_CORS_ALLOW_ORIGINS",
    "FRONTEND_DIR",
    "FRONTEND_URL",
    "HOST",
    "PORT",
    "Settings",
    "get_settings",
]
