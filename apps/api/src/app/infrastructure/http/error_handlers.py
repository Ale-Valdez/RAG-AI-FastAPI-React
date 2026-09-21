from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import DomainError, NotFoundError, TenantIsolationError, UnauthenticatedError
from app.infrastructure.http.responses.api_response import error_body

_HTTP_STATUS_ENVELOPE = {
    404: ("NOT_FOUND", "Not found"),
    405: ("METHOD_NOT_ALLOWED", "Method not allowed"),
}


def _is_product_route(request: Request) -> bool:
    return request.url.path.startswith("/api/v1")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        if _is_product_route(request):
            return JSONResponse(
                error_body("VALIDATION_ERROR", "Request validation failed"),
                status_code=422,
            )
        return JSONResponse({"detail": exc.errors()}, status_code=422)

    @app.exception_handler(UnauthenticatedError)
    async def unauthenticated(request: Request, exc: UnauthenticatedError) -> JSONResponse:
        if _is_product_route(request):
            return JSONResponse(
                error_body("UNAUTHENTICATED", str(exc) or "Authentication required"),
                status_code=401,
            )
        return JSONResponse({"detail": str(exc)}, status_code=401)

    @app.exception_handler(TenantIsolationError)
    async def tenant_isolation(request: Request, exc: TenantIsolationError) -> JSONResponse:
        if _is_product_route(request):
            return JSONResponse(
                error_body("TENANT_ISOLATION", str(exc) or "Forbidden"),
                status_code=403,
            )
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(NotFoundError)
    async def not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        if _is_product_route(request):
            return JSONResponse(
                error_body("NOT_FOUND", str(exc) or "Not found"),
                status_code=404,
            )
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError) -> JSONResponse:
        if _is_product_route(request):
            return JSONResponse(
                error_body("DOMAIN_RULE_VIOLATION", str(exc) or "Conflict"),
                status_code=409,
            )
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if _is_product_route(request):
            code, message = _HTTP_STATUS_ENVELOPE.get(
                exc.status_code, ("HTTP_ERROR", "Request failed")
            )
            return JSONResponse(error_body(code, message), status_code=exc.status_code)
        detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
        return JSONResponse({"detail": detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        if _is_product_route(request):
            return JSONResponse(
                error_body("INTERNAL_ERROR", "Internal server error"),
                status_code=500,
            )
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
