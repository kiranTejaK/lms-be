"""
Centralized exception hierarchy for the application.

Provides structured, domain-specific exceptions that map cleanly to HTTP
status codes. Use these throughout services instead of raising raw
HTTPException — the global handler in main.py converts them automatically.
"""

import structlog
from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Base Application Exception
# ---------------------------------------------------------------------------

class AppException(Exception):
    """Base exception for all application-level errors."""

    def __init__(self, detail: str, status_code: int = 500):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class NotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    def __init__(self, resource: str = "Resource", resource_id: str | int = ""):
        detail = f"{resource} not found" if not resource_id else f"{resource} with id '{resource_id}' not found"
        super().__init__(detail=detail, status_code=404)


class ConflictException(AppException):
    """Raised on duplicate / uniqueness constraint violations."""

    def __init__(self, detail: str = "Resource already exists"):
        super().__init__(detail=detail, status_code=409)


class ForbiddenException(AppException):
    """Raised when the user lacks permission for the requested action."""

    def __init__(self, detail: str = "You do not have permission to perform this action"):
        super().__init__(detail=detail, status_code=403)


class UnauthorizedException(AppException):
    """Raised when authentication fails or credentials are invalid."""

    def __init__(self, detail: str = "Could not validate credentials"):
        super().__init__(detail=detail, status_code=401)


class ValidationException(AppException):
    """Raised for business-rule validation failures."""

    def __init__(self, detail: str = "Validation error"):
        super().__init__(detail=detail, status_code=422)


# ---------------------------------------------------------------------------
# Global Exception Handlers — register via `register_exception_handlers(app)`
# ---------------------------------------------------------------------------

def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Convert AppException subclasses into structured JSON responses."""
    logger.warning(
        "app_exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=str(request.url),
    )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — prevents stack traces leaking to clients."""
    logger.error(
        "unhandled_exception",
        error=str(exc),
        path=str(request.url),
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Catches automatic Pydantic v2 validation errors and reformats them cleanly."""
    # V2 introduces a simpler dict format via .errors()
    errors = exc.errors()

    logger.warning(
        "request_validation_failed",
        path=str(request.url),
        errors=errors
    )

    # Flatten or structure the errors nicely for your frontend developers
    readable_errors = [
        {"field": " -> ".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
        for err in errors
    ]

    return JSONResponse(
        status_code=422,
        content={"detail": "Validation Failed", "errors": readable_errors}
    )

def register_exception_handlers(app) -> None:
    """Attach all global exception handlers to the FastAPI application."""
    app.add_exception_handler(AppException, app_exception_handler)

    # Catches Pydantic Input/Request failures
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # Catch-all for everything else
    app.add_exception_handler(Exception, generic_exception_handler)
