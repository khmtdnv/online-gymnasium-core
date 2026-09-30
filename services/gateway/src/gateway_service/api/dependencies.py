import secrets
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from gateway_service.application.auth import (
    GetCurrentUserHandler,
    LoginHandler,
    RefreshHandler,
)
from gateway_service.application.backoffice import (
    CreateUserHandler,
    LinkParentStudentHandler,
    ListUsersHandler,
)


def get_login_handler(request: Request) -> LoginHandler:
    return LoginHandler(
        uow_factory=request.app.state.uow_factory,
        password_service=request.app.state.password_service,
        token_service=request.app.state.token_service,
    )


def get_refresh_handler(request: Request) -> RefreshHandler:
    return RefreshHandler(
        uow_factory=request.app.state.uow_factory,
        token_service=request.app.state.token_service,
    )


def get_current_user_handler(request: Request) -> GetCurrentUserHandler:
    return GetCurrentUserHandler(
        uow_factory=request.app.state.uow_factory,
        token_service=request.app.state.token_service,
    )


def require_backoffice_service_token(
    request: Request,
    x_backoffice_service_token: Annotated[str | None, Header()] = None,
) -> None:
    expected_token = request.app.state.settings.backoffice_service_token

    if not x_backoffice_service_token or not secrets.compare_digest(
        x_backoffice_service_token, expected_token
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid backoffice service token",
        )


def get_create_user_handler(request: Request) -> CreateUserHandler:
    return CreateUserHandler(
        uow_factory=request.app.state.uow_factory,
        password_service=request.app.state.password_service,
    )


def get_list_users_handler(request: Request) -> ListUsersHandler:
    return ListUsersHandler(uow_factory=request.app.state.uow_factory)


def get_link_parent_student_handler(request: Request) -> LinkParentStudentHandler:
    return LinkParentStudentHandler(uow_factory=request.app.state.uow_factory)
