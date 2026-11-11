"""Consistent error responses: {"error": {"code": ..., "message": ..., "details": ...}}."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("meetpilot.errors")


class AppError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: Any = None,
                 headers: dict[str, str] | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def not_found(what: str = "Resource") -> AppError:
    return AppError(404, "not_found", f"{what} not found.")


def forbidden(message: str = "You do not have permission to do this.") -> AppError:
    return AppError(403, "forbidden", message)


def bad_request(message: str, code: str = "bad_request", details: Any = None) -> AppError:
    return AppError(400, code, message, details)


def conflict(message: str, code: str = "conflict", details: Any = None) -> AppError:
    return AppError(409, code, message, details)


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


_STATUS_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
                 405: "method_not_allowed", 409: "conflict", 413: "payload_too_large", 429: "rate_limited"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code,
                            headers=exc.headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(_body(code, message), status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e.get("loc", ()) if p != "body"), "message": e.get("msg", "")}
                   for e in exc.errors()]
        return JSONResponse(_body("validation_error", "Some fields are invalid.", details), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Log the type and route only: messages can contain transcript text or provider payloads.
        log.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url.path, exc_info=exc)
        return JSONResponse(_body("internal_error", "Something went wrong on the server."), status_code=500)
