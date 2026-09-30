from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from gateway_service.api.dependencies import (
    get_create_user_handler,
    get_link_parent_student_handler,
    get_list_users_handler,
    require_backoffice_service_token,
)
from gateway_service.application.backoffice import (
    CreateUserCommand,
    CreateUserHandler,
    LinkParentStudentCommand,
    LinkParentStudentHandler,
    ListUsersHandler,
)
from gateway_service.application.errors import (
    EmailAlreadyExistsError,
    InvalidParentStudentRolesError,
    UserNotFoundError,
)
from gateway_service.domain.user import Role

router = APIRouter(
    prefix="/internal/backoffice",
    tags=["backoffice"],
    dependencies=[Depends(require_backoffice_service_token)],
    include_in_schema=False,
)


@dataclass(frozen=True, slots=True)
class CreateUserRequest:
    email: str
    password: str
    role: Role


@dataclass(frozen=True, slots=True)
class UserResponse:
    id: UUID
    email: str
    role: Role
    is_active: bool


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_user(
    request_model: CreateUserRequest,
    handler: Annotated[CreateUserHandler, Depends(get_create_user_handler)],
) -> UserResponse:
    command = CreateUserCommand(
        email=request_model.email,
        password=request_model.password,
        role=request_model.role,
    )

    try:
        result = await handler.handle(command)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email already exists"
        ) from exc

    return UserResponse(
        id=result.id,
        email=result.email,
        role=result.role,
        is_active=result.is_active,
    )


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    handler: Annotated[ListUsersHandler, Depends(get_list_users_handler)],
) -> list[UserResponse]:
    result = await handler.handle()

    users_list = []
    for user in result:
        users_list.append(
            UserResponse(
                id=user.id,
                email=user.email,
                role=user.role,
                is_active=user.is_active,
            )
        )

    return users_list


@router.put(
    "/parents/{parent_id}/children/{student_id}",
    status_code=status.HTTP_201_CREATED,
)
async def link_parent_student(
    parent_id: UUID,
    student_id: UUID,
    handler: Annotated[
        LinkParentStudentHandler, Depends(get_link_parent_student_handler)
    ],
) -> Response:
    try:
        created = await handler.handle(LinkParentStudentCommand(parent_id, student_id))
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User was not found",
        ) from exc
    except InvalidParentStudentRolesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Users must have parent and student roles",
        ) from exc

    return Response(
        status_code=(status.HTTP_201_CREATED if created else status.HTTP_204_NO_CONTENT)
    )
