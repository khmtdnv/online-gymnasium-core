class ApplicationException(Exception):
    pass


class AuthenticationError(ApplicationException):
    pass


class EmailAlreadyExistsError(ApplicationException):
    pass


class UserNotFoundError(ApplicationException):
    pass


class InvalidParentStudentRolesError(ApplicationException):
    pass
