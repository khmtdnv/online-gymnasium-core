from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from gateway_service.api.dependencies import (
    get_current_user_handler,
    get_login_handler,
    get_refresh_handler,
)
from gateway_service.application.auth import (
    GetCurrentUserCommand,
    GetCurrentUserHandler,
    LoginCommand,
    LoginHandler,
    RefreshCommand,
    RefreshHandler,
)
from gateway_service.application.errors import AuthenticationError
from gateway_service.domain.user import Role

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True, slots=True)
class LoginRequest:
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class LoginResponse:
    access_token: str


@router.post("/login", response_model=LoginResponse)
async def login(
    request: Request,
    request_model: LoginRequest,
    handler: Annotated[LoginHandler, Depends(get_login_handler)],
    response: Response,
):
    command = LoginCommand(email=request_model.email, password=request_model.password)
    try:
        result = await handler.handle(command)
        response.set_cookie(
            key="refresh_token",
            value=result.refresh_token,
            httponly=True,
            samesite="strict",
            path="/api/v1/auth",
            max_age=request.app.state.settings.refresh_token_ttl_seconds,
        )
        return LoginResponse(result.access_token)

    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc


@dataclass(frozen=True, slots=True)
class RefreshResponse:
    access_token: str


@router.post("/refresh", response_model=RefreshResponse)
async def refresh(
    request: Request,
    handler: Annotated[RefreshHandler, Depends(get_refresh_handler)],
    response: Response,
    refresh_token: Annotated[str | None, Cookie()] = None,
):
    try:
        if not refresh_token:
            raise AuthenticationError

        command = RefreshCommand(refresh_token)
        result = await handler.handle(command)
        response.set_cookie(
            key="refresh_token",
            value=result.refresh_token,
            httponly=True,
            samesite="strict",
            path="/api/v1/auth",
            max_age=request.app.state.settings.refresh_token_ttl_seconds,
        )
        return RefreshResponse(result.access_token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc


@dataclass(frozen=True, slots=True)
class GetCurrentUserResponse:
    id: UUID
    email: str
    role: Role


@router.get("/me", response_model=GetCurrentUserResponse)
async def get_current_user(
    handler: Annotated[GetCurrentUserHandler, Depends(get_current_user_handler)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> GetCurrentUserResponse:
    try:
        if credentials is None:
            raise AuthenticationError

        command = GetCurrentUserCommand(credentials.credentials)
        result = await handler.handle(command)

        return GetCurrentUserResponse(
            id=result.id,
            email=result.email,
            role=result.role,
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token invalid or not provided",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
