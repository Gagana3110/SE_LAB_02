"""Standard error format from the SAD (Section 4.3): {error: {code, message, details?}, requestId}."""

import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


def _error(request: Request, status: int, message: str, details=None, headers=None) -> JSONResponse:
    error = {"code": status, "message": message}
    if details:
        error["details"] = details
    body = {"error": error, "requestId": getattr(request.state, "request_id", None)}
    return JSONResponse(status_code=status, content=body, headers=headers)


def register_error_handling(app: FastAPI) -> None:
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return _error(request, exc.status_code, str(exc.detail), headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Input values are left out so that a submitted password can never be echoed back.
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
                   for e in exc.errors()]
        return _error(request, 400, "Invalid request", details=details)
