import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.exceptions import HTTPException as StarletteHTTPException

from gateway_service.api.router import router
from gateway_service.application.ports.password_service import PasswordService
from gateway_service.application.ports.token_service import TokenService
from gateway_service.application.ports.unit_of_work import UnitOfWork
from gateway_service.config import GatewaySettings

logger = logging.getLogger(__name__)


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    request_id = request.state.request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": request_id,
            }
        },
        headers={**(headers or {}), "X-Request-ID": request_id},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await app.state.engine.dispose()


def create_app(
    settings: GatewaySettings,
    engine: AsyncEngine,
    uow_factory: Callable[[], UnitOfWork],
    password_service: PasswordService,
    token_service: TokenService,
) -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        codes = {
            401: "authentication_error",
            403: "forbidden",
            404: "not_found",
            409: "conflict",
            422: "validation_error",
        }
        message = (
            exc.detail
            if isinstance(exc.detail, str) and exc.status_code < 500
            else "Request failed"
        )
        return _error_response(
            request,
            status_code=exc.status_code,
            code=codes.get(exc.status_code, "http_error"),
            message=message,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        return _error_response(
            request,
            status_code=422,
            code="validation_error",
            message="Request validation failed",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        logger.exception(
            "Unhandled Gateway error request_id=%s", request.state.request_id
        )
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="Internal server error",
        )

    app.include_router(router)
    app.state.settings = settings
    app.state.engine = engine
    app.state.uow_factory = uow_factory
    app.state.password_service = password_service
    app.state.token_service = token_service

    return app
