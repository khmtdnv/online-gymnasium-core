class ApplicationException(Exception):
    pass


class ScheduleConflict(ApplicationException):
    pass


class LessonNotFound(ApplicationException):
    pass


class VersionConflict(ApplicationException):
    pass


class IdempotencyKeyReuse(ApplicationException):
    pass
