from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.application.health.get_health import GetHealth
from app.application.health.get_readiness import GetReadiness


def build_health_router(get_health: GetHealth, get_readiness: GetReadiness) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health() -> dict[str, str]:
        result = get_health.execute()
        return {"status": result.status, "service": result.service}

    @router.get("/ready")
    async def ready() -> JSONResponse:
        result = await get_readiness.execute()
        payload = {
            "status": result.status,
            "probes": {item.name: item.ok for item in result.probes},
        }
        status_code = 200 if result.status == "ok" else 503
        return JSONResponse(payload, status_code=status_code)

    return router
