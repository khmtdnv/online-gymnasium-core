import hashlib
import json
from datetime import date as Date
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from schedule_service.api.dependencies import (
    get_cancel_lesson_handler,
    get_create_lesson_handler,
    get_list_lessons_handler,
    get_update_lesson_handler,
)
from schedule_service.application.cancel_lesson import CancelLessonCommand, CancelLessonHandler
from schedule_service.application.create_lesson import CreateLessonCommand, CreateLessonHandler
from schedule_service.application.errors import IdempotencyKeyReuse, LessonNotFound, ScheduleConflict, VersionConflict
from schedule_service.application.list_lessons import ListLessonsHandler, ListLessonsQuery
from schedule_service.application.update_lesson import UpdateLessonCommand, UpdateLessonHandler
from schedule_service.domain.lesson import InvalidLessonInterval, LessonAlreadyCanceled

router = APIRouter(prefix="/lessons", tags=["lessons"])


class CreateLessonRequest(BaseModel):
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime


class UpdateLessonRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    expected_version: int


class CancelLessonRequest(BaseModel):
    expected_version: int


class LessonResponse(BaseModel):
    id: int
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime
    status: str
    version: int


@router.post("", status_code=201, response_model=LessonResponse)
async def create_lesson(
    request_model: CreateLessonRequest,
    handler: Annotated[CreateLessonHandler, Depends(get_create_lesson_handler)],
    idempotency_key: Annotated[str | None, Header()] = None,
):
    payload = request_model.model_dump(mode="json")
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    request_hash = hashlib.sha256(serialized.encode()).hexdigest()
    command = CreateLessonCommand(
        class_id=request_model.class_id,
        teacher_id=request_model.teacher_id,
        subject_id=request_model.subject_id,
        starts_at=request_model.starts_at,
        ends_at=request_model.ends_at,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    try:
        response = await handler.handle(command)
    except InvalidLessonInterval as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="starts_at must be before ends_at",
        ) from exc
    except ScheduleConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lesson conflicts with existing schedule",
        ) from exc
    except IdempotencyKeyReuse as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency key was already used for another request",
        ) from exc

    return response


@router.patch("/{lesson_id}", response_model=LessonResponse)
async def update_lesson(
    lesson_id: int,
    request_model: UpdateLessonRequest,
    handler: Annotated[UpdateLessonHandler, Depends(get_update_lesson_handler)],
):
    command = UpdateLessonCommand(
        lesson_id=lesson_id,
        starts_at=request_model.starts_at,
        ends_at=request_model.ends_at,
        expected_version=request_model.expected_version,
    )
    try:
        return await handler.handle(command)
    except InvalidLessonInterval as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="starts_at must be before ends_at",
        ) from exc
    except LessonNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        ) from exc
    except VersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lesson version conflict",
        ) from exc
    except ScheduleConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lesson conflicts with existing schedule",
        ) from exc


@router.post("/{lesson_id}/cancel", response_model=LessonResponse)
async def cancel_lesson(
    lesson_id: int,
    request_model: CancelLessonRequest,
    handler: Annotated[CancelLessonHandler, Depends(get_cancel_lesson_handler)],
):
    command = CancelLessonCommand(
        lesson_id=lesson_id,
        expected_version=request_model.expected_version,
    )
    try:
        return await handler.handle(command)
    except LessonAlreadyCanceled as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lesson is already canceled",
        ) from exc
    except LessonNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        ) from exc
    except VersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Lesson version conflict",
        ) from exc


@router.get("", response_model=list[LessonResponse])
async def list_lessons(
    class_id: int,
    date: Date,
    handler: Annotated[ListLessonsHandler, Depends(get_list_lessons_handler)],
):
    query = ListLessonsQuery(class_id=class_id, day=date)
    return await handler.handle(query)
