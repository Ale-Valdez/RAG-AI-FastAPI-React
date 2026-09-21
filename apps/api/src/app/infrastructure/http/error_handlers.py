from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.domain.errors import DomainError, TenantIsolationError


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(TenantIsolationError)
    async def tenant_isolation(_request, exc: TenantIsolationError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(DomainError)
    async def domain_error(_request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=409)
