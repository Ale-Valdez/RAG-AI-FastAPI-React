from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, NotFoundError, TenantIsolationError, UnauthenticatedError
from app.infrastructure.http.responses.api_response import error_body


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
