from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.application.health.get_health import GetHealth
from app.application.health.get_readiness import GetReadiness, ReadinessProbe
from app.infrastructure.config.settings import Settings, load_settings
from app.infrastructure.health.postgres_probe import PostgresProbe
from app.infrastructure.health.qdrant_probe import QdrantProbe
from app.infrastructure.health.redis_probe import RedisProbe
from app.infrastructure.http.error_handlers import register_error_handlers
from app.infrastructure.http.health_router import build_health_router


def default_probes(settings: Settings) -> list[ReadinessProbe]:
    return [
        PostgresProbe(settings.database_url),
        RedisProbe(settings.redis_url),
        QdrantProbe(settings.qdrant_url),
    ]


def create_app(
    *,
    settings: Settings | None = None,
    readiness_probes: list[ReadinessProbe] | None = None,
) -> FastAPI:
    loaded = settings or load_settings()
    probes = readiness_probes if readiness_probes is not None else default_probes(loaded)
    application = FastAPI(title=loaded.app_name)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=loaded.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(application)
    application.include_router(
        build_health_router(GetHealth(loaded.app_name), GetReadiness(probes))
    )
    return application
