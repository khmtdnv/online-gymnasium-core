from fastapi import Request

from schedule_service.application.create_lesson import CreateLessonHandler


def get_create_lesson_handler(request: Request) -> CreateLessonHandler:
    return CreateLessonHandler(uow_factory=request.app.state.uow_factory)
