class AppError(Exception):
    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


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


class ProcessingError(Exception):
    """A file could not be parsed. Stored on the document; not an HTTP error."""
