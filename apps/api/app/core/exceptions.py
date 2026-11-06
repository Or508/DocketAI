class AppError(Exception):
    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Sign in required.") -> None:
        super().__init__(message, status_code=401, code="unauthenticated")


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, status_code=403, code="forbidden")


class NotFoundError(AppError):
    def __init__(self, message: str = "Not found") -> None:
        super().__init__(message, status_code=404, code="not_found")


class BadRequestError(AppError):
    def __init__(self, message: str, code: str = "bad_request") -> None:
        super().__init__(message, status_code=400, code=code)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, code="conflict")


class UnprocessableError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=422, code="unprocessable")


class GoneError(AppError):
    def __init__(self, message: str = "This link is no longer active. Contact the office for a new one.") -> None:
        super().__init__(message, status_code=410, code="link_unavailable")


class RateLimitError(AppError):
    def __init__(self, message: str = "Too many messages on this link.") -> None:
        super().__init__(message, status_code=429, code="rate_limited")


class ProcessingError(Exception):
    """A file could not be parsed. Stored on the document; not an HTTP error."""
