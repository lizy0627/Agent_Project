from pydantic import BaseModel, Field


class AuthRegisterRequest(BaseModel):
    """Request body for creating a local user."""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=72)


class AuthLoginRequest(BaseModel):
    """Request body for logging in."""

    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=72)


class AuthUserResponse(BaseModel):
    """Public user profile returned to the frontend."""

    id: str
    username: str
    auth_enabled: bool = True


class AuthTokenResponse(BaseModel):
    """JWT login/register response."""

    success: bool = True
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class AuthMeResponse(BaseModel):
    """Current authenticated user response."""

    success: bool = True
    user: AuthUserResponse
