from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
from threading import Lock
import time

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse

from backend.app.core.config import Settings, get_settings
from backend.app.core.exceptions import AgentError, ErrorCode, error_response
from backend.app.schemas.auth import (
    AuthLoginRequest,
    AuthLogoutResponse,
    AuthMeResponse,
    AuthRegisterRequest,
    AuthTokenResponse,
    AuthUserResponse,
)
from backend.app.services.user_store import User, UserAlreadyExistsError, UserStore


router = APIRouter(prefix="/auth", tags=["auth"])
store_lock = Lock()
cached_user_store: UserStore | None = None
cached_user_store_signature: str | None = None


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    username: str
    auth_enabled: bool = True


def get_user_store(settings: Settings = Depends(get_settings)) -> UserStore:
    """Return the configured local user store singleton."""

    global cached_user_store, cached_user_store_signature

    signature = str(settings.auth_db_path)
    with store_lock:
        if cached_user_store is None or cached_user_store_signature != signature:
            cached_user_store = UserStore(settings.auth_db_path)
            cached_user_store_signature = signature
        return cached_user_store


@router.post("/register", response_model=AuthTokenResponse)
def register(
    request: AuthRegisterRequest,
    settings: Settings = Depends(get_settings),
    store: UserStore = Depends(get_user_store),
) -> AuthTokenResponse | JSONResponse:
    """Create a user and return a JWT."""

    try:
        user = store.create_user(request.username, request.password)
    except UserAlreadyExistsError:
        return auth_error("Username already exists.", status.HTTP_409_CONFLICT)

    return token_response(user, settings)


@router.post("/login", response_model=AuthTokenResponse)
def login(
    request: AuthLoginRequest,
    settings: Settings = Depends(get_settings),
    store: UserStore = Depends(get_user_store),
) -> AuthTokenResponse | JSONResponse:
    """Verify credentials and return a JWT."""

    user = store.verify_user(request.username, request.password)
    if user is None:
        return auth_error("Invalid username or password.", status.HTTP_401_UNAUTHORIZED)
    return token_response(user, settings)


def get_current_user(
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    store: UserStore = Depends(get_user_store),
) -> CurrentUser:
    """Return the current user, or a dev user when auth is disabled."""

    if not settings.auth_enabled:
        return CurrentUser(
            user_id=settings.auth_dev_user_id,
            username="dev",
            auth_enabled=False,
        )

    token = bearer_token(authorization)
    if token is None:
        raise unauthorized()

    try:
        payload = decode_jwt(token, settings.auth_jwt_secret)
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        raise unauthorized() from None

    user = store.get_user_by_id(user_id)
    if user is None:
        raise unauthorized()

    return CurrentUser(user_id=str(user.id), username=user.username, auth_enabled=True)


@router.get("/me", response_model=AuthMeResponse)
def get_me(current_user: CurrentUser = Depends(get_current_user)) -> AuthMeResponse:
    """Return the current user profile."""

    return AuthMeResponse(user=public_user(current_user))


@router.post("/logout", response_model=AuthLogoutResponse)
def logout(_: CurrentUser = Depends(get_current_user)) -> AuthLogoutResponse:
    """Acknowledge logout for stateless JWT clients."""

    return AuthLogoutResponse(message="Logged out.")


def token_response(user: User, settings: Settings) -> AuthTokenResponse:
    current_user = CurrentUser(user_id=str(user.id), username=user.username, auth_enabled=settings.auth_enabled)
    return AuthTokenResponse(
        access_token=create_jwt(user, settings),
        user=public_user(current_user),
    )


def public_user(user: CurrentUser) -> AuthUserResponse:
    return AuthUserResponse(
        id=user.user_id,
        username=user.username,
        auth_enabled=user.auth_enabled,
    )


def bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def create_jwt(user: User, settings: Settings) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "exp": now + settings.auth_token_expire_minutes * 60,
    }
    return encode_jwt(payload, settings.auth_jwt_secret)


def encode_jwt(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = ".".join(
        [
            base64url_json(header),
            base64url_json(payload),
        ]
    )
    signature = sign(signing_input, secret)
    return f"{signing_input}.{signature}"


def decode_jwt(token: str, secret: str) -> dict:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token shape.")

    signing_input = ".".join(parts[:2])
    expected_signature = sign(signing_input, secret)
    if not hmac.compare_digest(parts[2], expected_signature):
        raise ValueError("Invalid token signature.")

    header = json.loads(base64url_decode(parts[0]))
    if header.get("alg") != "HS256":
        raise ValueError("Unsupported token algorithm.")

    payload = json.loads(base64url_decode(parts[1]))
    if int(payload.get("exp", 0)) < int(time.time()):
        raise ValueError("Token expired.")
    return payload


def sign(signing_input: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), signing_input.encode("utf-8"), hashlib.sha256).digest()
    return base64url_bytes(digest)


def base64url_json(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return base64url_bytes(raw)


def base64url_bytes(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def base64url_decode(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def auth_error(message: str, status_code: int) -> JSONResponse:
    return error_response(
        AgentError(message=message, code=ErrorCode.AUTH_ERROR, status_code=status_code),
        message=message,
    )
