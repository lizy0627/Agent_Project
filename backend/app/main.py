from threading import Timer
from time import perf_counter
import webbrowser

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
import uvicorn

from backend.app.api.auth import get_user_store, router as auth_router
from backend.app.api.chat import get_conversation_store, router as chat_router
from backend.app.api.documents import get_document_store, router as documents_router
from backend.app.api.mcp import router as mcp_router
from backend.app.core.config import (
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    FRONTEND_DIR,
    FRONTEND_URL,
    HOST,
    PORT,
    get_settings,
)
from backend.app.core.exceptions import (
    AgentError,
    AuthenticationRequiredError,
    InvalidArgumentsError,
    NotFoundError,
    UnknownAgentError,
    error_payload,
    error_response,
)
from backend.app.core.logger import get_logger, setup_logging
from backend.app.core.safe_logging import safe_log_data


setup_logging()
logger = get_logger(__name__)


def frontend_page() -> Response:
    """Return the frontend entry page."""

    index_file = FRONTEND_DIR / "index.html"
    if not index_file.exists():
        logger.warning("Frontend entry file is missing: %s", index_file)
        error = NotFoundError("Frontend entry file is missing.")
        return JSONResponse(status_code=404, content=error_payload(error))

    return FileResponse(index_file)


def create_app() -> FastAPI:
    """Create the FastAPI application and register routes/static files."""

    settings = get_settings()
    get_user_store(settings)
    get_conversation_store(settings)
    get_document_store(settings)
    app = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router)
    app.include_router(chat_router)
    app.include_router(documents_router)
    app.include_router(mcp_router)

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

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        started_at = perf_counter()
        request_info = {
            "method": request.method,
            "path": request.url.path,
            "query": dict(request.query_params),
            "client": request.client.host if request.client else None,
        }
        logger.info("User request started: %s", safe_log_data(request_info))
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "User request failed: method=%s path=%s duration_ms=%.2f",
                request.method,
                request.url.path,
                (perf_counter() - started_at) * 1000,
            )
            raise

        logger.info(
            "User request finished: method=%s path=%s status=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            (perf_counter() - started_at) * 1000,
        )
        return response

    @app.exception_handler(AgentError)
    async def agent_error_handler(_, exc: AgentError) -> JSONResponse:
        logger.info("Agent error handled: code=%s status=%s", exc.code, exc.status_code)
        return error_response(exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_, exc: RequestValidationError) -> JSONResponse:
        logger.info("Request validation failed: errors=%s", len(exc.errors()))
        return error_response(InvalidArgumentsError())

    @app.exception_handler(HTTPException)
    async def http_error_handler(_, exc: HTTPException) -> JSONResponse:
        logger.info("HTTP error handled: status=%s", exc.status_code)
        if exc.status_code == 401:
            return error_response(AuthenticationRequiredError(), headers=exc.headers)
        if exc.status_code == 404:
            return error_response(NotFoundError(), status_code=exc.status_code, headers=exc.headers)
        error = InvalidArgumentsError() if 400 <= exc.status_code < 500 else UnknownAgentError()
        return error_response(error, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unknown_error_handler(_, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled application error")
        error = UnknownAgentError()
        return error_response(error)

    return app


app = create_app()


def open_browser() -> None:
    """Open the local frontend after the development server starts."""

    webbrowser.open(FRONTEND_URL)


if __name__ == "__main__":
    settings = get_settings()
    if settings.auto_open_browser:
        Timer(1.0, open_browser).start()
    uvicorn.run(app, host=HOST, port=PORT)
