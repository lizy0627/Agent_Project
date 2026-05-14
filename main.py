from threading import Timer
import webbrowser

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from app.api.chat import router as chat_router
from app.core.config import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    CORS_ALLOW_ORIGINS,
    FRONTEND_DIR,
    FRONTEND_URL,
    HOST,
    PORT,
)
from app.core.errors import AgentError, UnknownAgentError
from app.core.logger import get_logger, setup_logging


setup_logging()
logger = get_logger(__name__)


def frontend_page() -> Response:
    """Return the frontend entry page."""

    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        logger.warning("Frontend entry file is missing: %s", index_file)
        return JSONResponse(
            status_code=404,
            content={"success": False, "error": "Frontend files are not available."},
        )

    return FileResponse(index_file)


def create_app() -> FastAPI:
    """Create the FastAPI application and register routes/static files."""

    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ALLOW_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)

    if FRONTEND_DIR.exists():
        app.mount(
            "/frontend",
            StaticFiles(directory=FRONTEND_DIR),
            name="frontend",
        )
    else:
        logger.warning(
            "Skip static file mount because frontend directory is missing: %s",
            FRONTEND_DIR,
        )

    app.add_api_route("/ui", frontend_page, methods=["GET"], include_in_schema=False)

    @app.exception_handler(AgentError)
    async def agent_error_handler(_, exc: AgentError) -> JSONResponse:
        logger.info("Agent error handled: code=%s status=%s", exc.code, exc.status_code)
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
        logger.info("Request validation failed: errors=%s", len(exc.errors()))
        return JSONResponse(
            status_code=422,
            content={"success": False, "error": "Invalid request. Please check the request body."},
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_, exc: HTTPException) -> JSONResponse:
        logger.info("HTTP error handled: status=%s", exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": detail},
        )

    @app.exception_handler(Exception)
    async def unknown_error_handler(_, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        error = UnknownAgentError()
        return JSONResponse(
            status_code=error.status_code,
            content={"success": False, "error": error.message},
        )

    return app


app = create_app()


def open_browser() -> None:
    """Open the local frontend after the development server starts."""

    webbrowser.open(FRONTEND_URL)


if __name__ == "__main__":
    Timer(1.0, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT)
