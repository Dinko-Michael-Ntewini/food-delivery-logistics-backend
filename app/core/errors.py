"""One safe error envelope for framework, domain and database failures."""
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException

from app.core.exceptions import ApplicationError
from app.schemas.error import ErrorResponse

CODES = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT",
         422: "VALIDATION_ERROR", 500: "INTERNAL_ERROR"}
ERROR_RESPONSES = {code: {"model": ErrorResponse, "description": HTTPStatus(code).phrase}
                   for code in (401, 403, 404, 409, 422, 500)}


def error_response(status: int, message: str, *, code: str | None = None, details=None, headers=None):
    return JSONResponse(status_code=status, headers=headers, content={"error": {
        "code": code or CODES.get(status, "HTTP_ERROR"), "message": message, "details": details}})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def domain_error(request: Request, exc: ApplicationError):
        return error_response(exc.status_code, exc.message, code=exc.code)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else HTTPStatus(exc.status_code).phrase
        if exc.status_code >= 500:
            message = "Internal server error"
        return error_response(exc.status_code, message, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Never serialize input, ctx, exception representations, or the request body.
        details = [{"location": list(err["loc"]), "type": err["type"],
                    "message": "Invalid value" if err["type"] == "value_error" else err["msg"]}
                   for err in exc.errors()]
        return error_response(422, "Request validation failed", details=details)

    @app.exception_handler(IntegrityError)
    async def integrity_error(request: Request, exc: IntegrityError):
        return error_response(409, "Resource conflicts with a database constraint")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        return error_response(500, "Internal server error")
