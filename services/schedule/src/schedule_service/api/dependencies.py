from fastapi import Request

from schedule_service.application.cancel_lesson import CancelLessonHandler
from schedule_service.application.create_lesson import CreateLessonHandler
from schedule_service.application.update_lesson import UpdateLessonHandler


def get_create_lesson_handler(request: Request) -> CreateLessonHandler:
    return CreateLessonHandler(uow_factory=request.app.state.uow_factory)


def get_cancel_lesson_handler(request: Request) -> CancelLessonHandler:
    return CancelLessonHandler(uow_factory=request.app.state.uow_factory)


def get_update_lesson_handler(request: Request) -> UpdateLessonHandler:
    return UpdateLessonHandler(uow_factory=request.app.state.uow_factory)
