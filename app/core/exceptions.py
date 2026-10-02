"""Small application exceptions carrying only client-safe messages."""


class ApplicationError(Exception):
    status_code = 422
    code = "VALIDATION_ERROR"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class NotFoundError(ApplicationError):
    status_code = 404
    code = "NOT_FOUND"


class ForbiddenError(ApplicationError):
    status_code = 403
    code = "FORBIDDEN"


class ConflictError(ApplicationError):
    status_code = 409
    code = "CONFLICT"


class InvalidTransitionError(ConflictError):
    code = "INVALID_TRANSITION"
