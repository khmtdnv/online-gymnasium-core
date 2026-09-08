from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from schedule_service.api.dependencies import get_create_lesson_handler
from schedule_service.application.create_lesson import CreateLessonCommand, CreateLessonHandler
from schedule_service.application.errors import ScheduleConflict
from schedule_service.domain.lesson import InvalidLessonInterval

router = APIRouter(prefix="/lessons", tags=["lessons"])


class CreateLessonRequest(BaseModel):
    class_id: int
    teacher_id: int
    subject_id: int
    starts_at: datetime
    ends_at: datetime


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
):
    command = CreateLessonCommand(
        class_id=request_model.class_id,
        teacher_id=request_model.teacher_id,
        subject_id=request_model.subject_id,
        starts_at=request_model.starts_at,
        ends_at=request_model.ends_at,
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
    return response
